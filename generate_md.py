import json

def generate_md_table():
    try:
        with open('lark_mcp_tools.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        tools = data.get('result', {}).get('tools', [])
        
        md_lines = []
        md_lines.append("# Lark MCP Tools Reference")
        md_lines.append("")
        md_lines.append("| Tool Name | Description | Key Parameters |")
        md_lines.append("| :--- | :--- | :--- |")
        
        for tool in tools:
            name = tool.get('name', '')
            desc = tool.get('description', '').replace('\n', ' ')
            
            # Extract parameters
            schema = tool.get('inputSchema', {}).get('properties', {})
            params_list = []
            
            # Helper to get fields from a section like 'data', 'params', 'path'
            def get_fields(section_name):
                section = schema.get(section_name, {})
                if not section:
                    return []
                props = section.get('properties', {})
                return [f"`{p}`" for p in props.keys()]

            # Common Lark API sections
            data_fields = get_fields('data')
            if data_fields:
                params_list.append(f"**data**: {', '.join(data_fields)}")
                
            params_fields = get_fields('params')
            if params_fields:
                params_list.append(f"**params**: {', '.join(params_fields)}")
                
            path_fields = get_fields('path')
            if path_fields:
                params_list.append(f"**path**: {', '.join(path_fields)}")
            
            params_str = "<br>".join(params_list) if params_list else "None"
            
            md_lines.append(f"| `{name}` | {desc} | {params_str} |")
            
        content = "\n".join(md_lines)
        
        with open('LARK_MCP_TOOLS.md', 'w', encoding='utf-8') as f:
            f.write(content)
            
        print("Markdown table generated in LARK_MCP_TOOLS.md")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    generate_md_table()
