import subprocess
import json
import sys
import os

def run_mcp_export():
    """
    Export MCP tools by spawning the Lark MCP server.
    Secrets MUST come from environment variables and must never be hardcoded.
    """

    client_id = os.getenv("LARK_MCP_CLIENT_ID")
    client_secret = os.getenv("LARK_MCP_CLIENT_SECRET")
    domain = os.getenv("LARK_MCP_DOMAIN", "https://open.larksuite.com/")
    use_oauth = os.getenv("LARK_MCP_USE_OAUTH", "true").lower() in ("1", "true", "yes", "y")

    if not client_id or not client_secret:
        print("Error: missing LARK_MCP_CLIENT_ID / LARK_MCP_CLIENT_SECRET in environment (.env).")
        return

    cmd = ["npx", "-y", "@larksuiteoapi/lark-mcp", "mcp", "-a", client_id, "-s", client_secret, "-d", domain]
    if use_oauth:
        cmd.append("--oauth")
    
    print(f"Starting MCP server: {' '.join(cmd)}")
    
    try:
        # Start the process
        # Force UTF-8 encoding for environment
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            shell=True,
            encoding='utf-8', # Explicitly use utf-8 for pipe reading
            errors='replace',  # Handle decoding errors gracefully
            env=env
        )
        
        # 1. Initialize
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "cursor-exporter", "version": "1.0.0"}
            }
        }
        
        print("Sending initialize...")
        process.stdin.write(json.dumps(init_req) + "\n")
        process.stdin.flush()
        
        # Read initialize response
        init_resp_line = process.stdout.readline()
        print(f"Init response: {len(init_resp_line)} chars")
        # init_resp = json.loads(init_resp_line)
        
        # 2. Initialized notification
        initialized_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        process.stdin.write(json.dumps(initialized_notif) + "\n")
        process.stdin.flush()
        
        # 3. List tools
        list_tools_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        
        print("Sending tools/list...")
        process.stdin.write(json.dumps(list_tools_req) + "\n")
        process.stdin.flush()
        
        # Read tools response
        # Note: server might send other notifications, so we need to loop until we get id 2
        tools_data = None
        while True:
            line = process.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
                if msg.get("id") == 2:
                    tools_data = msg
                    break
            except json.JSONDecodeError:
                continue
        
        if tools_data:
            with open("lark_mcp_tools.json", "w", encoding="utf-8") as f:
                json.dump(tools_data, f, indent=2, ensure_ascii=False)
            print("Successfully exported tools to lark_mcp_tools.json")
        else:
            print("Failed to get tools response")

        process.terminate()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run_mcp_export()
