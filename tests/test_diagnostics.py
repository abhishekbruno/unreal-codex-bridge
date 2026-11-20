import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from doctor import check_engine, result_code
from unreal_session import parse_toolsets, validate_inputs, verify_process_identity
from bridge_mcp import MCPError


class DiagnosticTests(unittest.TestCase):
    def test_status_exit_codes(self):
        self.assertEqual(result_code([{'status':'PASS'}]),0)
        self.assertNotEqual(result_code([{'status':'FAIL'}]),0)
        self.assertNotEqual(result_code([{'status':'BLOCKED'}]),0)
        self.assertNotEqual(result_code([{'status':'NOT TESTED'}]),0)

    def test_missing_plugin_is_not_compatible(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'Engine/Build').mkdir(parents=True)
            (root/'Engine/Build/Build.version').write_text(json.dumps({'MajorVersion':5,'MinorVersion':8}))
            with self.assertRaisesRegex(ValueError,'UnrealEditor|plugin'):
                check_engine(root)

    def test_wrong_version_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/'Engine/Build').mkdir(parents=True)
            (root/'Engine/Build/Build.version').write_text(json.dumps({'MajorVersion':5,'MinorVersion':7}))
            with self.assertRaisesRegex(ValueError,'5.8'):
                check_engine(root)

    def test_toolset_description_bullets_not_toolsets(self):
        self.assertEqual(parse_toolsets('- A.Tools: description\n- GetInfo: text\n- B.More: desc'),['A.Tools','B.More'])

    def test_required_argument_and_type_validation(self):
        schema={'type':'object','properties':{'name':{'type':'string'}},'required':['name']}
        for args in ({},{'name':5}):
            with self.assertRaises(MCPError): validate_inputs(schema,args)
        validate_inputs(schema,{'name':'test'})

    def test_process_identity_rejects_same_name_other_directory(self):
        process={'ExecutablePath':'D:/UE/Engine/Binaries/Win64/UnrealEditor.exe',
                 'CommandLine':'UnrealEditor.exe "D:/Wrong/Test.uproject"'}
        with self.assertRaises(MCPError): verify_process_identity(process,Path('D:/Right/Test.uproject'),Path('D:/UE'))


if __name__=='__main__': unittest.main()
