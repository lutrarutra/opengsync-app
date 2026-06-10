from codeflower_db.models import CommandVariant, ParamSpec
from codeflower_db.types import ParameterType, FileRelation

def compile_command_string(variant: CommandVariant) -> str | None:
    """
    Compiles a CLI command string from a CommandVariant and its parameters.
    Example output: `cp --recursive {recursive} {src} {dst}`
    """
    if not variant.command:
        return None
        
    command_name = variant.command.name
    
    params = [p for p in variant.parameters]
    
    params.sort(key=lambda p: p.position if p.position is not None else float('inf'))
    
    parts = [command_name]
    
    for param in params:
        param_str = ""
        
        if param.prefix:
            param_str += param.prefix
            if param.separate:
                param_str += " "
        
        value_placeholder = f"{{{param.name}}}"
        
        if param.is_array:
            value_placeholder = f"[{value_placeholder}...]"
            
        param_str += value_placeholder
            
        parts.append(param_str)
        
    return " ".join(parts).strip() if parts else None


def compile_usage_string(variant: CommandVariant) -> str | None:
    """
    Compiles a CLI usage help string from a CommandVariant and its parameters.
    Example output:
    Usage: cp [OPTIONS] {src} {dst}
    
    Positional Arguments:
      {src}                  Source path (Required, Type: path)
      {dst}                  Destination path (Required, Type: path)
      
    Options:
      --recursive {recursive}  Recursively copy (Type: boolean)
    """
    if not variant.command:
        return None
    
    positionals: list[ParamSpec] = []
    options: list[ParamSpec] = []
    
    for param in variant.parameters:
        if param.prefix:
            options.append(param)
        else:
            positionals.append(param)
            
    # Sort positionals by position, options alphabetically
    positionals.sort(key=lambda p: p.position if p.position is not None else float('inf'))
    options.sort(key=lambda p: p.name)
    
    # 1. Build Usage line
    usage_line = f"Usage: {variant.invoke_cmd or '<invoke command not defined>'}"
    if options:
        usage_line += " [OPTIONS]"
        
    for p in positionals:
        val = f"{{{p.name}}}"
        if p.is_array: 
            val = f"[{val}...]"
        if not p.is_required: 
            val = f"[{val}]"
        usage_line += f" {val}"
        
    lines = [usage_line, ""]
    
    # 2. Helper to build the left column (e.g. `--prefix {value}`)
    def get_left_col(p):
        s = ""
        if p.prefix:
            s += p.prefix
            if p.separate:
                s += " "
        val = f"{{{p.name}}}"
        if p.is_array:
            val = f"[{val}...]"
        s += val
        return s
        
    # 3. Collect rows and find the longest left column to align the text
    param_data = []
    max_left_len = 0
    for p in positionals + options:
        left_str = get_left_col(p)
        max_left_len = max(max_left_len, len(left_str))
        
        desc = p.description or "No description provided."
        
        # Add constraints info
        constraints = []
        if p.is_required:
            constraints.append("Required")
            
        if p.type == ParameterType.PATH:
            k = ','.join(p.io_spec.extensions if p.io_spec else [])
            constraints.append(f"Type: {p.type} [{k}]")
        else:
            constraints.append(f"Type: {p.type}")
            
        if constraints:
            desc += f" ({', '.join(constraints)})"
            
        param_data.append((p, left_str, desc))
        
    # Give it exactly 4 spaces of padding, but cap it at 40 chars width
    left_col_width = min(max_left_len + 4, 40)
    
    # 4. Assemble the final text
    if positionals:
        lines.append("Positional Arguments:")
        for p, left_str, desc in param_data:
            if not p.prefix:
                lines.append(f"  {left_str.ljust(left_col_width)}{desc}")
        lines.append("")
        
    if options:
        lines.append("Options:")
        for p, left_str, desc in param_data:
            if p.prefix:
                lines.append(f"  {left_str.ljust(left_col_width)}{desc}")
                
    return "\n".join(lines).strip()

def compile_cwl(variant: CommandVariant) -> dict | None:
    """
    Compiles a CWL (Common Workflow Language) CommandLineTool dictionary 
    from a CommandVariant and its parameters.
    """
    if not variant.command:
        return None
        
    cwl_dict = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "baseCommand": variant.command.name,
        "inputs": {},
        "outputs": {}
    }
    
    if variant.command.description:
        cwl_dict["doc"] = variant.command.description

    # Helper function to map codeflower types to CWL types
    def get_cwl_type(param: ParamSpec) -> str:
        param_type = param.type.value if hasattr(param.type, 'value') else str(param.type)
        if param_type == "path":
            # In CWL, files/paths are usually treated as 'File' or 'Directory'
            # Assuming 'File' for simplicity, but could be dynamic
            t = "File" 
        elif param_type == "string":
            t = "string"
        elif param_type == "numeric":
            # Could be float or int; CWL supports both, we default to float
            t = "float" 
        elif param_type == "boolean":
            t = "boolean"
        else:
            t = "string"
            
        if param.is_array:
            t = f"{t}[]"
            
        if not param.is_required:
            t = f"{t}?"
            
        return t

    # Group parameters by their roles
    inputs: list[ParamSpec] = []
    outputs: list[ParamSpec] = []
    regular_params: list[ParamSpec] = []
    
    for param in variant.parameters:
        if param.type == ParameterType.PATH:
            if param.path_role == FileRelation.INPUT:
                inputs.append(param)
            elif param.path_role == FileRelation.OUTPUT:
                outputs.append(param)
            else:
                # Fallback if path_role somehow isn't set
                regular_params.append(param)
        else:
            regular_params.append(param)

    # Compile Inputs (Files and standard parameters)
    for param in inputs + regular_params:
        input_binding = {}
        
        if param.prefix:
            input_binding["prefix"] = param.prefix
            input_binding["separate"] = param.separate
            
        if param.position is not None:
            input_binding["position"] = param.position
            
        if param.item_separator and param.is_array:
            input_binding["itemSeparator"] = param.item_separator

        param_def: dict = {
            "type": get_cwl_type(param),
        }
        
        if param.description:
            param_def["doc"] = param.description

        if input_binding:
            param_def["inputBinding"] = input_binding
            
        if param.default_value is not None and "value" in param.default_value:
            param_def["default"] = param.default_value["value"]

        # Only add extension constraints for files
        if param.type == ParameterType.PATH and param.io_spec and param.io_spec.extensions:
            # CWL handles format with 'format', but an array of matching extensions
            # is often put in extension constraints depending on the parser.
            param_def["format"] = param.io_spec.extensions

        cwl_dict["inputs"][param.name] = param_def

    # Compile Outputs
    for param in outputs:
        output_binding = {}
        
        # Typically, CWL outputs require a glob pattern to know which file to capture
        # If the output parameter takes a prefix/position, it might be dynamically defined by an input,
        # but often it's just a statically generated filename string or a glob based on the param name.
        if param.default_value and "value" in param.default_value:
            output_binding["glob"] = param.default_value["value"]
        else:
            # Fallback glob using the parameter name as a placeholder
            output_binding["glob"] = f"$({{{param.name}}})"

        param_def = {
            "type": get_cwl_type(param),
            "outputBinding": output_binding
        }
        
        if param.description:
            param_def["doc"] = param.description
            
        if param.io_spec and param.io_spec.extensions:
            param_def["format"] = param.io_spec.extensions

        cwl_dict["outputs"][param.name] = param_def

    return cwl_dict