import os
import re
import sys

class PT_Parser:
    def __init__(self,path):
        
        #Initialization
        self.module_definitions = {}
        self.package_definitions = {}

        self.output_ports = {}
        self.input_ports = {}
        self.internal_sigs = {}
        
        self.parameters = {}

        self.dont_trace_modules = [] 
        self.dont_trace_ports = {}

        #Reading Modules
        self.read_definitions(path)
        self.set_ports("input")
        self.set_ports("output")
        self.set_internal_sigs()
        self.set_parameters()
        self.parse_command_line_arguments()

    def read_definitions(self,path):
        path=os.path.expandvars(path)
        if os.path.isdir(path) :
            for root, dirs, files in os.walk(path):
                for file in files:
                    if file.endswith(('.v', '.sv')):
                        file_path = os.path.join(root, file)
                        self._read_modules(file_path)
        
        elif os.path.isfile(path) and path.endswith(('.v', '.sv')) :            
            self._read_modules(path)

        else :
            incdir_paths, f_paths = self.detect_lines(path)
            for path in incdir_paths:
                path=os.path.expandvars(path)
                for filename in os.listdir(path):
                    if filename.endswith('.v') or filename.endswith('.sv'):
                        file_path = os.path.join(path.strip(), filename.strip())
                        self._read_modules(file_path)
    
            for path in f_paths:
                path=os.path.expandvars(path)
                files_from_metafile = self._get_files(path)
                for v_sv_fil in files_from_metafile :
                    self._read_modules(v_sv_fil)


    def _get_files(self,file_path:str) : # -> list
        lines = []
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()  # Strip the newline character
                line = os.path.expandvars(line)
                if (not line.startswith('#')) and os.path.isfile(line) and line.endswith(('.v', '.sv')) :  
                # Check if the line doesn't start with '#'
                    lines.append(line)  # Add the line to the list
        return lines


    def detect_lines(self,file_path):
        incdir_paths = []
        f_paths = []

        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if line.startswith('-incdir'):
                    # Extract path after '-incdir'
                    path = line.split('-incdir')[1].strip()
                    incdir_paths.append(path)
                elif line.startswith('-f'):
                    # Extract path after '-f'
                    path = line.split('-f')[1].strip()
                    f_paths.append(path)

        return incdir_paths, f_paths


    def _read_modules(self,file_path):
        with open(file_path, encoding="utf-8") as f:
            file_content = f.read()
            comment_pattern = re.compile(r'//.*?$', re.MULTILINE)
            content = comment_pattern.sub('', file_content)
            modules = re.findall(r'\bmodule\s+(\w+)', content)
            for module in modules:
                if module in self.module_definitions:
                    # raise ValueError(f"File {file_path} redefines module {module} already defined.")
                    print( f"WARNING: {file_path} redfining {module} already defined")
                self.module_definitions[module] = self._extract_module_definition(content, module)
            
            packages = re.findall(r'\bpackage\s+(\w+)', content)
            for package in packages:
                if package in self.package_definitions:
                    raise ValueError(f"File {file_path} redefines package {package} already defined.")
                self.package_definitions[package] = self._extract_package_definition(content, package)

    def _extract_module_definition(self, file_content, module_name):
        module_pattern = re.compile(r'(\bmodule\b\s+' + re.escape(module_name) + r'\b.*?)(\bendmodule\b)', re.DOTALL)
        match = module_pattern.search(file_content)
        if match:
            return match.group(0).strip()
        else:
            raise ValueError(f"Module '{module_name}' definition not found in the file.")
        
    def _extract_package_definition(self, file_content, package_name):
        package_pattern = re.compile(r'(\bpackage\b\s+' + re.escape(package_name) + r'\b.*?)(\bendpackage\b)', re.DOTALL)
        match = package_pattern.search(file_content)
        if match:
            return match.group(0).strip()
        else:
            raise ValueError(f"Package '{package_name}' definition not found in the file.") 

        
    def set_parameters(self):
        for package_name, definition in self.package_definitions.items():
            self.parameters[package_name]=self._parse_parameters(definition)
        for module_name, definition in self.module_definitions.items():
            self.parameters[module_name] = self._parse_parameters(definition)
        

    def set_ports(self, direction="input"):
        target_dict = self.input_ports if direction == "input" else self.output_ports
        for module_name, definition in self.module_definitions.items():
            target_dict[module_name] = self._parse_ports(definition, direction)
            

    def _parse_ports(self, module_definition, direction):
        ports_pattern = r'\bmodule\b.*?(?:\((.*?)\))?\s*\((.*?)\);'
        module_declaration_match = re.search(ports_pattern, module_definition, re.DOTALL)
        
        if not module_declaration_match:
            raise ValueError("Module declaration not found in the definition.")
        
        port_list = re.split(r',\s*(?![^\[]*\])', module_declaration_match.group(2).strip())
        all_ports = self._extract_ports_from_declaration(port_list,direction,module_definition)
        
        # Filter ports based on the direction
        filtered_ports = [port for port, port_dir in all_ports.items() if (direction == 'input' and port_dir == 'input') or (direction == 'output' and port_dir == 'output')]
        return filtered_ports
    

    def _parse_parameters(self,definition):

        parameters={}

        # Extract parameters
        param_pattern =  re.compile(r'(?:#\s*\(\s*)?parameter\s+(\w+)\s*=\s*([\S\'_]+(?:\s*,\s*(?:parameter)?\s*\w+\s*=\s*[\S\'_]+\s*)*)\s*(?:\)\s*|;)')
        

        param_matches = param_pattern.findall(definition)

        # Extract localparameters
        localparam_pattern =  re.compile(r'localparam\s+(\w+)\s*=\s*([\S\'_]+(?:\s*,\s*\w+\s*=\s*[\S\'_]+\s*)*)\s*;')
        localparam_matches = localparam_pattern.findall(definition) 
        
        for match_list in [param_matches,localparam_matches]:
            for match in match_list:
                parameters[match[0]] = match[1].split(',')[0].strip()

                params = [param.strip() for param in match[1].split(',')[1:]]

                for param in params:
                    key, val = param.split('=')
                    parameters[key.strip()] = val.strip()
        return parameters
    
    def _extract_ports_from_declaration(self, port_list,parsing_direction, module_definition):
        ports = {}
        port_pattern = r'(?:\s*(input|output)\s*)?(?:(?:wire|reg|logic)\s+)?(?:\[[^\]]+\]\s*)?(\w+)'

        for i, port in enumerate(port_list):
            port_match = re.match(port_pattern, port.strip())
            # print( port)
            if port_match:
                direction, port_name = port_match.groups()
                prev_port_name= re.match(port_pattern, port_list[i-1].strip()).group(2) if i > 0 else None
                
                if direction != parsing_direction :
                    if direction is None:
                        if len(ports) ==0 :
                            continue
                        elif len(ports)>0 and prev_port_name not in ports:
                            break
        
                        else:
                            ports[port_name] = ports.get(prev_port_name,None)
                    else:
                        continue
                else :
                    ports[port_name] = ports.get(prev_port_name,None) if direction is None else direction
        
        if len(ports) == 0:
            # Update port directions based on additional declarations outside the module declaration
            ports = self._update_port_directions(ports, parsing_direction, module_definition)
                    
        return ports

    def _update_port_directions(self, ports, direction, module_definition):
        # Pattern to match port declaration lines, including single or multiple declarations
        pattern = fr'{direction}\s*([^;]+?);'
        matches = re.findall(pattern, module_definition, re.DOTALL)
        
        for match in matches:
            # Process each declaration, considering potential bus specifiers
            port_declarations = re.split(r',\s*', match.strip())
        
            for decl in port_declarations:
                # Extract port name, considering optional bus specifier
                port_name_match = re.search(r'(?:\[[^\]]+\]\s*)?\s*(\w+)', decl)
       
                if port_name_match:
                    port_name = port_name_match.group(1)
                    if port_name and port_name not in ['input', 'output']:  # Exclude keywords
                        ports[port_name] = direction

        return ports


    def set_internal_sigs(self):
        for module_name, definition in self.module_definitions.items():
            self.internal_sigs[module_name] = self._get_internal_sigs(definition)

    def _get_internal_sigs(self, module_definition):
        # Initialize an empty list to store found internal signals
        internal_signals = []

        # Patterns to match signal declarations
        # This pattern matches 'wire' or 'reg', followed by optional bus specifiers, followed by one or more signal names
        signal_pattern = r'\b(wire|reg|logic)\s*(?:\[.*?\]\s*)?(\w+(?:\s*,\s*\w+)*);'

        # Find all matches in the module definition
        matches = re.findall(signal_pattern, module_definition)
        # Process each match to extract all signal names
        for match in matches:
            # Split the signal names by commas, in case of multiple signals declared in one line
            signals = [sig.strip() for sig in match[1].split(',')]
            internal_signals.extend(signals)

        return internal_signals
        
    def parse_command_line_arguments(self):
        # Look for the "-dtms" argument in the command line arguments
        if "-dtms" in sys.argv:
            dtms_index = sys.argv.index("-dtms") + 1
            if dtms_index < len(sys.argv):
                dtms_arg = sys.argv[dtms_index]
                self.dont_trace_modules = [module.strip() for module in dtms_arg.split(',')]

        # Look for the "-dtps" argument in the command line arguments
        if "-dtps" in sys.argv:
            dtps_index = sys.argv.index("-dtps") + 1
            if dtps_index < len(sys.argv):
                dtps_arg = sys.argv[dtps_index]
                for entry in dtps_arg.split(','):
                    module, port = [item.strip() for item in entry.split(':')]
                    if module in self.dont_trace_ports:
                        self.dont_trace_ports[module].append(port)
                    else:
                        self.dont_trace_ports[module] = [port]

if __name__ == '__main__' :
    
    if len(sys.argv) < 1 :
        print("Must supply folder location as arg1")
        
    else :
        
        directory = sys.argv[1]
    
        parser = PT_Parser(directory)
        
        print("Modules: ",parser.module_definitions.keys())
        print("Packages: ",parser.package_definitions.keys())
        print("Inputs: ",parser.input_ports)
        print("Outputs: ",parser.output_ports)
        print("Internals: ",parser.internal_sigs)
        print("Parameters: ",parser.parameters)
        print()
        print()
        print("DNT Ports",parser.dont_trace_ports)
        print("DNT Modules",parser.dont_trace_modules)