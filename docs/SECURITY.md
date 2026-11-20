# Security boundary

This is a **local development** integration, not a multi-user hosted service. Epic's Unreal MCP endpoint is unauthenticated. Do not expose it to the public internet or to an untrusted LAN. Even a local process may be able to invoke powerful editor tools. Tool approval is not equivalent to sandboxing.

Run on a trusted machine, from a trusted project folder, with a clean version-control checkpoint. Review prompts and tool operations, especially deletes, renames, actor/asset bulk mutations, and privileged Python execution inside Unreal Editor. Disable the integration while handling untrusted projects.

Remote ChatGPT web sessions cannot directly access `127.0.0.1` on your PC. A remote deployment needs a separately designed, authenticated gateway with authorization, origin controls, rate limits, transport security and narrowly scoped tool access. This package deliberately does **not** expose such a gateway.

Experimental Unreal MCP APIs change between engine releases. Test against your exact installed Unreal build before considering it reliable for production assets.
