"""Centralized automatic entity save system for Unreal Codex Bridge.

Permanently ensures automatic saving and persistence verification after
successful entity creation (Actors, Blueprints, Materials, Components, and Assets)
through Unreal MCP without requiring manual save requests.
"""
import inspect
import json
import os
from pathlib import Path
import time
from bridge_mcp import MCPError


ENTITY_CREATION_TOOLS = {
    ('SceneTools', 'add_to_scene_from_asset'): 'actor',
    ('SceneTools', 'add_to_scene_from_class'): 'actor',
    ('ActorTools', 'spawn_actor'): 'actor',
    ('ActorTools', 'spawn_actor_from_asset'): 'actor',
    ('BlueprintTools', 'create'): 'blueprint',
    ('MaterialTools', 'create_material'): 'material',
    ('MaterialTools', 'create_function'): 'material',
    ('MaterialTools', 'create_parameter_collection'): 'material',
    ('MaterialInstanceTools', 'create'): 'material_instance',
    ('ActorTools', 'add_component'): 'component',
    ('AssetTools', 'duplicate'): 'asset',
    ('AssetTools', 'create_asset'): 'asset',
    ('DataTableTools', 'create'): 'asset',
    ('CurveTableTools', 'create'): 'asset',
    ('StringTableTools', 'create'): 'asset',
    ('DataAssetTools', 'create'): 'asset',
    ('ControlRigTools', 'create'): 'asset',
    ('StateTreeTools', 'create'): 'asset',
}

GRAPH_CONSTRUCTION_TOOLS = {
    ('BlueprintTools', 'create_node'),
    ('BlueprintTools', 'delete_node'),
    ('BlueprintTools', 'connect_pins'),
    ('BlueprintTools', 'break_pins'),
    ('BlueprintTools', 'write_graph_dsl'),
    ('BlueprintTools', 'set_node_position'),
    ('BlueprintTools', 'add_variable'),
    ('BlueprintTools', 'remove_variable'),
    ('BlueprintTools', 'add_function_graph'),
    ('BlueprintTools', 'remove_function_graph'),
    ('BlueprintTools', 'add_component_bound_event'),
    ('BlueprintTools', 'set_create_event_function'),
    ('MaterialTools', 'add_expression'),
    ('MaterialTools', 'delete_expression'),
    ('MaterialTools', 'connect_expressions'),
    ('MaterialTools', 'disconnect_expressions'),
    ('MaterialTools', 'connect_to_output'),
    ('MaterialTools', 'disconnect_from_output'),
    ('MaterialTools', 'layout_expressions'),
}


def is_entity_creation_tool(toolset, tool_name):
    """Check if the given toolset and tool name perform entity creation."""
    short_ts = toolset.split('.')[-1]
    short_tool = tool_name.split('.')[-1]
    return (short_ts, short_tool) in ENTITY_CREATION_TOOLS


def is_graph_construction_tool(toolset, tool_name):
    """Check if the given toolset and tool name are part of graph construction."""
    short_ts = toolset.split('.')[-1]
    short_tool = tool_name.split('.')[-1]
    return (short_ts, short_tool) in GRAPH_CONSTRUCTION_TOOLS


def get_entity_type_for_tool(toolset, tool_name):
    """Return the entity type created by the tool, or None."""
    short_ts = toolset.split('.')[-1]
    short_tool = tool_name.split('.')[-1]
    return ENTITY_CREATION_TOOLS.get((short_ts, short_tool))


def extract_package_path(target):
    """Extract and normalize a /Game/... package path from an asset/actor reference.

    Rejects paths not starting with /Game/ or containing path traversal '..'.
    """
    if isinstance(target, dict):
        if 'refPath' in target:
            target = target['refPath']
        elif 'path' in target:
            target = target['path']
        elif 'asset_path' in target:
            target = target['asset_path']
        elif 'package_path' in target:
            target = target['package_path']
        elif 'new_path' in target:
            target = target['new_path']
        elif 'destination_path' in target:
            target = target['destination_path']
        else:
            raise ValueError(f"Cannot extract package path from dict reference: {target}")

    if not isinstance(target, str):
        raise ValueError(f"Expected string or dict reference, got: {type(target)}")

    target = target.replace('\\', '/')

    if not target.startswith('/Game/'):
        raise ValueError(f"Only /Game/ packages are supported, got: {target}")
    if '..' in target:
        raise ValueError(f"Path traversal '..' rejected in package path: {target}")

    # Remove subobject or instance separator (e.g., :PersistentLevel.Actor or :Default__BP_C)
    if ':' in target:
        target = target.split(':', 1)[0]

    # Remove asset name suffix if formatted as /Game/Folder/Asset.Asset
    last_slash = target.rfind('/')
    if last_slash != -1:
        prefix = target[:last_slash]
        base = target[last_slash + 1:]
        if '.' in base:
            base = base.split('.', 1)[0]
        target = f"{prefix}/{base}"
    elif '.' in target:
        target = target.split('.', 1)[0]

    target = target.rstrip('/')

    return target


class CreationTransaction:
    """Manages a multi-step entity creation transaction with checkpoints and final auto-save."""

    def __init__(self, manager, name='creation_transaction', entity_type=None,
                 entity_ref=None, package_path=None, owner_ref=None, validate_fn=None):
        self.manager = manager
        self.name = name
        self.entity_type = entity_type
        self.entity_ref = entity_ref
        self.package_path = package_path
        self.owner_ref = owner_ref
        self.validate_fn = validate_fn
        self.tracked_entities = []
        if entity_type and (entity_ref or package_path):
            self.register_entity(entity_type, entity_ref, package_path=package_path, owner_ref=owner_ref)

        self.checkpoints = []
        self.status = 'PENDING'
        self.committed = False
        self.start_time = time.time()

    def register_entity(self, entity_type, entity_ref=None, package_path=None, owner_ref=None):
        """Register an entity created during this transaction."""
        entry = {
            'entity_type': entity_type,
            'entity_ref': entity_ref,
            'package_path': package_path,
            'owner_ref': owner_ref,
            'timestamp': time.time(),
        }
        self.tracked_entities.append(entry)
        if not self.entity_type:
            self.entity_type = entity_type
        if not self.entity_ref and entity_ref:
            self.entity_ref = entity_ref
        if not self.package_path and package_path:
            self.package_path = package_path
        if not self.owner_ref and owner_ref:
            self.owner_ref = owner_ref

    def checkpoint(self, checkpoint_name, validate_fn=None):
        """Save a completed checkpoint after an entity reaches an intermediate valid state."""
        if self.committed:
            raise MCPError(f"Cannot record checkpoint '{checkpoint_name}' on committed transaction")

        fn = validate_fn or self.validate_fn
        if fn and callable(fn):
            fn_res = fn()
            if fn_res is False:
                raise MCPError(f"Validation failed before checkpoint '{checkpoint_name}'")

        packages_to_save = self._resolve_all_packages()
        if not packages_to_save:
            raise MCPError(f"No packages to save for checkpoint '{checkpoint_name}'")

        saved = []
        for pkg in packages_to_save:
            self.manager.save_package(pkg)
            saved.append(pkg)

        record = {
            'checkpoint': checkpoint_name,
            'time': time.time(),
            'packages_saved': saved,
            'status': 'SAVED',
        }
        self.checkpoints.append(record)
        return record

    def _resolve_all_packages(self):
        """Resolve all distinct package paths for tracked entities."""
        packages = set()
        if self.package_path:
            try:
                packages.add(extract_package_path(self.package_path))
            except ValueError:
                pass

        for entry in self.tracked_entities:
            try:
                pkgs = self.manager.resolve_packages_to_save(
                    entity_type=entry['entity_type'],
                    entity_ref=entry['entity_ref'],
                    owner_ref=entry['owner_ref'],
                    package_path=entry['package_path']
                )
                packages.update(pkgs)
            except Exception:
                if entry.get('package_path'):
                    try:
                        packages.add(extract_package_path(entry['package_path']))
                    except ValueError:
                        pass
        return sorted(packages)

    def commit(self, validate_fn=None):
        """Validate final state, automatically save all owning packages, and verify persistence."""
        if self.committed:
            return {'status': 'ALREADY_COMMITTED', 'transaction': self.name}

        fn = validate_fn or self.validate_fn
        if fn and callable(fn):
            fn_res = fn()
            if fn_res is False:
                raise MCPError(f"Validation failed before committing transaction '{self.name}'")

        packages = self._resolve_all_packages()
        if not packages:
            raise MCPError(f"No packages identified to save for transaction '{self.name}'")

        saved_packages = []
        verifications = []

        # Save all packages
        for pkg in packages:
            self.manager.save_package(pkg)
            saved_packages.append(pkg)

        # If primary entity is actor, also invoke save_actor if applicable
        if self.entity_type == 'actor' and self.entity_ref:
            try:
                self.manager.session.invoke('SceneTools', 'save_actor', actor=self.entity_ref)
            except Exception:
                pass

        # Verify persistence using Unreal MCP read
        for entry in self.tracked_entities:
            ent_type = entry.get('entity_type')
            ent_ref = entry.get('entity_ref')
            pkg = entry.get('package_path')
            if not pkg and ent_ref:
                try:
                    pkg = extract_package_path(ent_ref)
                except Exception:
                    pass
            if not pkg and packages:
                pkg = packages[0]

            v_res = self.manager.verify_persistence(
                entity_type=ent_type,
                entity_ref=ent_ref,
                package_path=pkg,
                owner_ref=entry.get('owner_ref')
            )
            verifications.append(v_res)

        self.committed = True
        self.status = 'COMMITTED'

        summary = {
            'status': 'COMMITTED',
            'transaction': self.name,
            'duration_sec': time.time() - self.start_time,
            'checkpoints': self.checkpoints,
            'packages_saved': saved_packages,
            'verifications': verifications,
        }
        self.manager.history.append(summary)
        return summary

    def abort(self, reason='Aborted'):
        """Abort transaction without saving partial or corrupted state."""
        self.status = 'ABORTED'
        self.committed = False
        summary = {
            'status': 'ABORTED',
            'transaction': self.name,
            'reason': str(reason),
            'checkpoints': self.checkpoints,
        }
        self.manager.history.append(summary)
        return summary

    def __enter__(self):
        self.manager._active_transaction = self
        self.status = 'ACTIVE'
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.manager._active_transaction = None
        if exc_type is not None:
            self.abort(reason=f"Exception raised: {exc_val}")
            return False
        if not self.committed:
            self.commit()
        return False


class AutoSaveManager:
    """Centralized AutoSave Manager for Unreal Codex Bridge."""

    def __init__(self, session, guard=None, project=None, engine=None, enabled=True):
        self.session = session
        self.guard = guard
        self.project = Path(project) if project else None
        self.engine = Path(engine) if engine else None
        self.enabled = enabled
        self._active_transaction = None
        self.history = []

    def is_in_transaction(self):
        """Check if a multi-step creation transaction is currently active."""
        return self._active_transaction is not None

    @property
    def current_transaction(self):
        """Return the active transaction, if any."""
        return self._active_transaction

    def transaction(self, name='entity_creation', entity_type=None,
                    entity_ref=None, package_path=None, owner_ref=None, validate_fn=None):
        """Create a new CreationTransaction context for multi-step entity creation."""
        return CreationTransaction(
            manager=self,
            name=name,
            entity_type=entity_type,
            entity_ref=entity_ref,
            package_path=package_path,
            owner_ref=owner_ref,
            validate_fn=validate_fn
        )

    def resolve_packages_to_save(self, entity_type, entity_ref=None, owner_ref=None, package_path=None):
        """Resolve the owning package(s) that must be saved for a given entity type.

        - Actors -> owning level and relevant external-actor packages.
        - Blueprints/materials/assets -> their asset packages.
        - Components -> owning Actor/Blueprint package.
        """
        packages = []

        if entity_type == 'actor':
            # 1. Determine owning level
            level_pkg = None
            try:
                current_level = self.session.invoke('SceneTools', 'get_current_level')
                if current_level and current_level.startswith('/Game/'):
                    level_pkg = extract_package_path(current_level)
            except Exception:
                pass

            # 2. Extract from actor ref if level unknown or to identify external actor package
            actor_pkg = None
            if entity_ref:
                try:
                    actor_pkg = extract_package_path(entity_ref)
                except Exception:
                    pass

            if level_pkg:
                packages.append(level_pkg)
            elif actor_pkg:
                # If actor_pkg contains __ExternalActors__, extract owning level before it
                if '__ExternalActors__' in actor_pkg:
                    base_level = actor_pkg.split('/__ExternalActors__', 1)[0]
                    packages.append(base_level)
                else:
                    packages.append(actor_pkg)

            # Check if actor_pkg is a distinct external-actor package (OFPA)
            if actor_pkg and actor_pkg not in packages:
                if '__ExternalActors__' in actor_pkg or '_ExternalActors_' in actor_pkg:
                    packages.append(actor_pkg)

        elif entity_type in ('blueprint', 'material', 'material_instance', 'asset'):
            target_pkg = package_path
            if not target_pkg and entity_ref:
                target_pkg = extract_package_path(entity_ref)
            if target_pkg:
                packages.append(extract_package_path(target_pkg))

        elif entity_type == 'component':
            # Components -> owning Actor or Blueprint package
            resolved_owner = owner_ref
            if not resolved_owner and entity_ref:
                # Try getting component owner actor via ActorTools
                try:
                    resolved_owner = self.session.invoke('ActorTools', 'get_component_actor', component=entity_ref)
                except Exception:
                    pass

            if resolved_owner:
                owner_str = json.dumps(resolved_owner) if isinstance(resolved_owner, dict) else str(resolved_owner)
                # Check if owner is a Blueprint CDO or Blueprint asset
                is_blueprint = any(x in owner_str for x in ('Default__', '.BP_', '_C', '/Blueprints/'))
                if is_blueprint:
                    bp_pkg = extract_package_path(resolved_owner)
                    packages.append(bp_pkg)
                else:
                    # Owner is an Actor in a level
                    actor_pkgs = self.resolve_packages_to_save(entity_type='actor', entity_ref=resolved_owner)
                    packages.extend(actor_pkgs)
            else:
                # Fallback: check current active level
                try:
                    current_level = self.session.invoke('SceneTools', 'get_current_level')
                    if current_level and current_level.startswith('/Game/'):
                        packages.append(extract_package_path(current_level))
                except Exception:
                    pass

        # Deduplicate while preserving order
        deduped = []
        for p in packages:
            norm = extract_package_path(p)
            if norm not in deduped:
                deduped.append(norm)

        if not deduped and package_path:
            deduped.append(extract_package_path(package_path))

        return deduped

    def save_package(self, package_path):
        """Automatically and safely save a single /Game/... package."""
        pkg = extract_package_path(package_path)

        # Check PIE running
        try:
            pie = self.session.invoke('EditorAppToolset', 'IsPIERunning')
            if pie is not False:
                raise MCPError('PIE running or unknown; save blocked')
        except MCPError:
            raise
        except Exception:
            pass

        # Delegate to EditorStateGuard if attached
        if self.guard:
            if hasattr(self.guard, 'authorize'):
                self.guard.authorize(pkg)
            self.guard.save(pkg)
            return True

        # Direct safe save
        save_result = self.session.invoke('AssetTools', 'save_assets', asset_paths=[pkg])
        if save_result is not True:
            raise MCPError(f"Save failed for package: {pkg}")

        dirty_check = self.session.invoke('AssetTools', 'is_dirty', asset_path=pkg)
        if dirty_check is not False:
            raise MCPError(f"Package remains dirty after save: {pkg}")

        return True

    def auto_save_entity(self, entity_type, entity_ref=None, owner_ref=None, package_path=None):
        """Automatically save the owning package(s) of an entity and verify persistence."""
        if not self.enabled:
            return {'status': 'SKIPPED', 'reason': 'AutoSaveManager disabled'}

        packages = self.resolve_packages_to_save(
            entity_type=entity_type,
            entity_ref=entity_ref,
            owner_ref=owner_ref,
            package_path=package_path
        )

        if not packages:
            raise MCPError(f"Could not determine owning package to save for {entity_type} entity")

        saved = []
        for pkg in packages:
            self.save_package(pkg)
            saved.append(pkg)

        # If actor, also save actor directly if supported
        if entity_type == 'actor' and entity_ref:
            try:
                self.session.invoke('SceneTools', 'save_actor', actor=entity_ref)
            except Exception:
                pass

        # Verify persistence using Unreal MCP read
        primary_pkg = packages[0]
        verification = self.verify_persistence(
            entity_type=entity_type,
            entity_ref=entity_ref,
            package_path=primary_pkg,
            owner_ref=owner_ref
        )

        record = {
            'status': 'SAVED_AND_VERIFIED',
            'entity_type': entity_type,
            'entity_ref': entity_ref,
            'packages_saved': saved,
            'verification': verification,
            'timestamp': time.time(),
        }
        self.history.append(record)
        return record

    def verify_persistence(self, entity_type, entity_ref=None, package_path=None, owner_ref=None):
        """Verify persistence using Unreal MCP read tools and package dirty state."""
        results = {'verified': False, 'checks': []}

        if package_path:
            pkg = extract_package_path(package_path)

            # 1. Dirty check
            dirty = self.session.invoke('AssetTools', 'is_dirty', asset_path=pkg)
            if dirty is not False:
                raise MCPError(f"Persistence verification failed: package {pkg} is dirty ({dirty})")
            results['checks'].append({'check': 'is_dirty', 'result': False, 'status': 'PASS'})

            # 2. Exists check
            exists = self.session.invoke('AssetTools', 'exists', path=pkg)
            if exists is not True:
                raise MCPError(f"Persistence verification failed: package {pkg} does not exist")
            results['checks'].append({'check': 'exists', 'result': True, 'status': 'PASS'})

            # 3. Readback via load_asset
            if entity_type in ('blueprint', 'material', 'material_instance', 'asset'):
                try:
                    loaded = self.session.invoke('AssetTools', 'load_asset', asset_path=pkg)
                    results['checks'].append({'check': 'load_asset', 'result': loaded, 'status': 'PASS'})
                    results['loaded_asset'] = loaded
                except Exception as e:
                    raise MCPError(f"Persistence verification failed to load asset {pkg}: {e}")

        # 4. Entity-specific Unreal MCP read verification
        if entity_type == 'actor' and entity_ref:
            try:
                xform = self.session.invoke('ActorTools', 'get_actor_transform', actor=entity_ref)
                results['checks'].append({'check': 'get_actor_transform', 'result': xform, 'status': 'PASS'})
            except Exception:
                pass

            try:
                label = self.session.invoke('ActorTools', 'get_label', actor=entity_ref)
                results['checks'].append({'check': 'get_label', 'result': label, 'status': 'PASS'})
            except Exception:
                pass

        elif entity_type == 'component' and owner_ref:
            try:
                comps = self.session.invoke('ActorTools', 'get_components', actor=owner_ref)
                results['checks'].append({'check': 'get_components', 'count': len(comps) if isinstance(comps, list) else 1, 'status': 'PASS'})
            except Exception:
                pass

        elif entity_type == 'blueprint' and entity_ref:
            try:
                cdo = self.session.invoke('BlueprintTools', 'get_default_object', blueprint=entity_ref)
                results['checks'].append({'check': 'get_default_object', 'result': cdo, 'status': 'PASS'})
            except Exception:
                pass

        # 5. On-disk file verification if project root is known
        if self.project and package_path:
            pkg = extract_package_path(package_path)
            content_dir = self.project.parent / 'Content'
            rel_path = pkg.removeprefix('/Game/')
            # Check for .uasset or .umap
            uasset_file = content_dir / (rel_path + '.uasset')
            umap_file = content_dir / (rel_path + '.umap')
            disk_file = umap_file if umap_file.is_file() else (uasset_file if uasset_file.is_file() else None)
            if disk_file and disk_file.stat().st_size > 0:
                results['checks'].append({
                    'check': 'disk_file_exists',
                    'path': str(disk_file),
                    'size': disk_file.stat().st_size,
                    'status': 'PASS'
                })

        results['verified'] = True
        return results

    def handle_post_invoke(self, toolset, tool_name, arguments, ret_val):
        """Hook called after session.invoke completes successfully."""
        if not self.enabled:
            return

        short_ts = toolset.split('.')[-1]
        short_tool = tool_name.split('.')[-1]

        if not is_entity_creation_tool(short_ts, short_tool):
            return

        entity_type = get_entity_type_for_tool(short_ts, short_tool)

        # Extract entity reference and package info from arguments & return value
        entity_ref = ret_val if isinstance(ret_val, dict) and 'refPath' in ret_val else None
        owner_ref = arguments.get('owner') or arguments.get('actor') or arguments.get('parent')

        package_path = None
        if 'folder_path' in arguments and 'asset_name' in arguments:
            package_path = f"{arguments['folder_path'].rstrip('/')}/{arguments['asset_name']}"
        elif 'new_path' in arguments:
            package_path = arguments['new_path']
        elif 'destination_path' in arguments:
            package_path = arguments['destination_path']
        elif 'path' in arguments and arguments['path'].startswith('/Game/'):
            package_path = arguments['path']
        elif entity_ref:
            try:
                package_path = extract_package_path(entity_ref)
            except Exception:
                pass

        # If a multi-step creation transaction is active:
        # Register the created entity to the transaction without interrupting graph construction!
        if self.is_in_transaction():
            self._active_transaction.register_entity(
                entity_type=entity_type,
                entity_ref=entity_ref,
                package_path=package_path,
                owner_ref=owner_ref
            )
            return

        # Outside of a transaction: standalone creation automatically saves owning package
        try:
            self.auto_save_entity(
                entity_type=entity_type,
                entity_ref=entity_ref,
                owner_ref=owner_ref,
                package_path=package_path
            )
        except Exception as exc:
            # Re-raise MCPError, log or suppress other errors if session is unconfigured
            if isinstance(exc, MCPError):
                raise
            raise MCPError(f"AutoSaveManager failed during automatic save of {entity_type}: {exc}") from exc
