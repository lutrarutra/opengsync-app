import re
from typing import Union

def is_browser_friendly(mimetype: str | None) -> bool:
    if not mimetype:
        return False
    return (
        mimetype.startswith("image/") or
        mimetype.startswith("text/") or
        mimetype in {
            "application/pdf",
            "application/javascript",
            "application/json",
        }
    )


def parse_markdown_template(raw_md: str) -> tuple[list[dict[str, Union[str, float | None]]], str]:
    """Parses parameters out and returns the cleaned template and parameter dicts."""
    param_block_match = re.search(r'(## 0\. Parameters.*?(?=## \d))', raw_md, re.DOTALL)
    
    params = []
    if param_block_match:
        param_block = param_block_match.group(1)
        template_md = raw_md.replace(param_block, '').strip()
        
        pattern = r'-\s*`([^`]+)`\s*:\s*(\w+)\s*:\s*\{(\w+)\}(?:\s*:\s*([\d.]+))?'
        
        for match in re.finditer(pattern, param_block):
            default_str = match.group(4)
            default_val = float(default_str) if default_str is not None else None
            
            params.append({
                'label': match.group(1),
                'type': match.group(2),
                'var_name': match.group(3),
                'default': default_val
            })
    else:
        template_md = raw_md
        
    return params, template_md