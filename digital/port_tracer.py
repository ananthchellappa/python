import re
import sys

from pt_parser import PT_Parser

class PortTracer:
    def __init__(self,path,top_module_name, out_to_trace):
        
        #Initialization
        parser = PT_Parser(directory)
        
        self.module_definitions = parser.module_definitions
        self.package_definitions = parser.package_definitions 

        self.output_ports = parser.output_ports
        self.input_ports = parser.input_ports
        self.internal_sigs = parser.internal_sigs
        
        self.parameters = parser.parameters

        self.dont_trace_modules = parser.dont_trace_modules 
        self.dont_trace_ports = parser.dont_trace_ports
        
        self.undefined_signals={}

        self.module_to_trace = top_module_name
        self.out_to_trace= out_to_trace
        self.hierarchy = ""


    def get_assignment_statement(self, module_name, signal_name):
        module_definition = self.module_definitions.get(module_name)
        if not module_definition:
            return "UD"

        signal_pattern = re.compile(r'\b' + re.escape(signal_name) + r'\s*=\s*([^;]+);', re.DOTALL)
        match = signal_pattern.search(module_definition)
        
        if (module_name in self.dont_trace_ports) and (signal_name in self.dont_trace_ports[module_name]):
            self.hierarchy=f"{self.hierarchy[:-1]}/DP:{signal_name}"
            return "DNT"
        
        elif module_name in self.dont_trace_modules:
            self.hierarchy=f"{self.hierarchy}DM:{module_name}/{signal_name}"
            return "DNT"
        
        elif match:
            return match.group(0)

        else :
            return None

    def trace_output_source(self, parent_module: str, signal_of_interest: str):

        parent_definition = self.module_definitions.get(parent_module)
        if not parent_definition:
            raise ValueError(f"Module '{parent_module}' not found.")

        # Extracting instances and their connections within the parent module
        instance_pattern = r'(\w+)\s+(?:#\s*\(\s*\.(?:.*?)\)\s*)?\s*(\w+)\s*\((.*?)\);'
        instances = re.findall(instance_pattern, parent_definition, re.DOTALL)
        
        for module_name, instance_name, connection_list in instances:
            # Skip the entry where 'module' is incorrectly interpreted as a module name
            if module_name == "module":
                continue
 
            connection_map = self._parse_instance_connections(connection_list, module_name)
            
            if connection_map is not None:
       
                for child_port, parent_signal in connection_map.items():
                    
                    if parent_signal == signal_of_interest:
                        
                        if parent_module == self.module_to_trace :
                            self.hierarchy=f"{instance_name}."
                        
                        elif module_name not in self.dont_trace_modules:
                            self.hierarchy+=f"{instance_name}."
                        
                        if module_name in self.dont_trace_ports :
                            for module,port in self.dont_trace_ports.items() :

                                if module == module_name and child_port in port:
                                    self.internal_sigs[parent_module]=list(set(self.internal_sigs[parent_module])-set(self.dont_trace_ports[module]))
                        
                        if module_name in self.dont_trace_modules:
                            self.internal_sigs[parent_module]=list(set(self.internal_sigs[parent_module])-set(self.output_ports[module_name]))
                        
                        return [module_name, instance_name, child_port]
            
            else :
                #print(f"{self.hierarchy}UD:{module_name}>{signal_of_interest}")              
                if '(' in connection_list and ')' in connection_list:
                    connections = re.findall(r'\.(\w+)\s*\(([^)]+)\)', connection_list)
                    if not self.undefined_signals.get(module_name) :
                        self.undefined_signals[module_name]={port[1] : f"{self.hierarchy}UD:{module_name}>{signal_of_interest}" for port in connections}
                
                self.internal_sigs[parent_module]=list(set(self.internal_sigs[parent_module])-set(port[1] for port in connections))
                self.output_ports[parent_module]=list(set(self.output_ports[parent_module])-set(port[1] for port in connections))
                
                if not self.output_ports[parent_module]  :
                    self.hierarchy= f"{self.hierarchy}UD:{module_name}>{signal_of_interest}"
                    return "UD","UD","UD"
        
        return []    

    def _get_port_order(self, module_name):
        module_definition = self.module_definitions.get(module_name)

        if not module_definition and module_name != self.module_to_trace:
            return None
            

        port_declaration_pattern =  r'\bmodule\b.*?(?:\((.*?)\))?\s*\((.*?)\);'
        
        match = re.search(port_declaration_pattern, module_definition, re.DOTALL)

        if not match:
            raise ValueError(f"Module declaration not found in module '{module_name}'.")

        port_declaration = match.group(2)
        port_order = [port.split()[-1] for port in port_declaration.split(',')]
        return port_order

    def get_port_signal_mapping(self, parent_module, instance_name):
        parent_definition = self.module_definitions.get(parent_module)
        
        if not parent_definition:
            raise ValueError(f"Module '{parent_module}' not found.")

        instance_pattern = r'(\w+)\s+(?:#\s*\(\s*\.(?:.*?)\)\s*)?\s*' + re.escape(instance_name) + r'\s*\((.*?)\);'
        
        match = re.search(instance_pattern, parent_definition, re.DOTALL)
        if not match:
            raise ValueError(f"Instance '{instance_name}' not found in module '{parent_module}'.")

        child_module_name, connection_list = match.groups()
        child_port_order = self._get_port_order(child_module_name)

        if '(' in connection_list and ')' in connection_list:
            return self._parse_named_port_assignments(connection_list)
        else:
            ports = [port.strip() for port in connection_list.split(',')]
            return dict(zip(child_port_order, ports))

    def _parse_instance_connections(self, connection_list, child_module_name):
        
        child_port_order = self._get_port_order(child_module_name)

        if child_port_order is not None : 
            if '(' in connection_list and ')' in connection_list:
                connections = re.findall(r'\.(\w+)\s*\(([^)]+)\)', connection_list)

                port_mapping = {child_port: parent_signal.strip() 
                                    for child_port, parent_signal in connections 
                                    if child_port in child_port_order}
                
            else:
                ports = [port.strip() for port in connection_list.split(',')]
                return dict(zip(child_port_order, ports))

            return port_mapping

    def _parse_named_port_assignments(self, connection_list):
        connections = re.findall(r'\.(\w+)\s*\(([^)]+)\)', connection_list)
        return {child_port: parent_signal.strip() for child_port, parent_signal in connections}

    def map_ports(self, parent_module:str, instance_name:str, raw_assignment:str):
        # Get the mapping of the child module's ports to the parent module's signals
        port_signal_mapping = self.get_port_signal_mapping(parent_module, instance_name)
        
        # Replace the child module's ports in the assignment statement with the corresponding parent signals
        for child_port, parent_signal in port_signal_mapping.items():
            # Replace child port with parent signal in the assignment statement
            # Using regex to ensure exact word match to avoid partial replacement
            raw_assignment = re.sub(r'\b{}\b'.format(re.escape(child_port)), parent_signal, raw_assignment)
        return raw_assignment

    def find_internal_signals_in_expression(self, module_name: str, assignment: str):
        
        if assignment == 'DNT' or assignment == "UD":
            return []        
        
        if module_name not in self.internal_sigs:
            raise ValueError(f"Module '{module_name}' does not exist or has no internal signals recorded.")
        
        # Extract the right-hand side (RHS) of the assignment
        
        _, rhs = assignment.split('=', 1)
        rhs = rhs.rstrip(';').strip()

        # This regex pattern matches Verilog identifiers (variables, ports, etc.)
        pattern = r'\b\w+\b'

        # Find all potential variable names in the RHS of the assignment
        variables = re.findall(pattern, rhs)

        # Filter variables to find those that are internal signals for the specified module
        internal_signals = [var for var in variables if var in self.internal_sigs[module_name] or var in self.output_ports[module_name] ]
        
        return internal_signals

    def identify_and_update_register_instance(self, parent_module):
        register_instance_name, register_module_name = self._find_register_instance(parent_module)
        
        if not register_instance_name:
            #print("No register block instance found.")
            
            return

        register_port_mapping = self._build_register_port_mapping(parent_module, register_instance_name, register_module_name)
        
        self.add_input_ports(parent_module, list(register_port_mapping.values()))

        self._update_other_instances(parent_module, register_port_mapping)

        self._remove_internal_signals(parent_module, list(register_port_mapping.values()))
    
        self._remove_register_instance(parent_module, register_instance_name)

    def _find_register_instance(self, parent_module):
        parent_def = self.module_definitions[parent_module]
        instances = re.findall(r'(\w+)\s+(?:#\s*\(\s*\.(?:.*?)\)\s*)?\s*(\w+)\s*\((.*?)\);', parent_def, re.DOTALL)

        for module_name, instance_name, _ in instances:
            if any(re.match(r'reg_\d\d', port) for port in self.output_ports.get(module_name, [])):
                return instance_name, module_name
        return None, None

    def _build_register_port_mapping(self, parent_module, instance_name, register_module_name):
        # Fetch the connection list from the instance statement in the parent module's definition
        instance_def_pattern = rf'\b{re.escape(instance_name)}\s*\((.*?)\);'
        instance_match = re.search(instance_def_pattern, self.module_definitions[parent_module], re.DOTALL)
        if not instance_match:
            raise ValueError(f"Instance {instance_name} not found in module {parent_module}.")
        connections_str = instance_match.group(1)

        port_signal_mapping = {}

        # Check if the instance uses named port assignments
        if re.search(r'\.\w+\s*\(', connections_str):
            # Parse named port assignments
            named_assignments = re.findall(r'\.(\w+)\s*\(([^)]+)\)', connections_str)
            for port, signal in named_assignments:
                if port in self.output_ports.get(register_module_name, []):
                    port_signal_mapping[port] = signal.strip()
        else:
            # Handle positional port assignments
            # Get the declared port order for the child module
            child_port_order = self._get_port_order(register_module_name)
            
            # Split the connections string into individual signals, considering bus slices
            connections = re.split(r',\s*(?![^()]*\))', connections_str.strip())

            output_ports = self.output_ports.get(register_module_name, [])
            for i, port in enumerate(child_port_order):
                if port in output_ports and i < len(connections):
                    port_signal_mapping[port] = connections[i].strip()

        return port_signal_mapping

    def add_input_ports(self, module_name, new_ports):
        if module_name not in self.input_ports:
            self.input_ports[module_name] = []
        for port in new_ports:
            if port not in self.input_ports[module_name]:
                self.input_ports[module_name].append(port)

    def _update_other_instances(self, parent_module, register_port_mapping):
        parent_def = self.module_definitions[parent_module]

        # Iterate through each mapping: new_port is a key, signal is a value
        for new_port, full_signal in register_port_mapping.items():
            # Remove bus suffix from the full signal name for the search pattern
            signal_base = re.sub(r'\[\d+:\d+\]$', '', full_signal)
            bus_suffix_pattern = r'(\[\d+:\d+\])?'

            # Create a pattern to find all occurrences of the signal, with or without bus specifiers
            pattern = rf'\b{re.escape(signal_base)}{bus_suffix_pattern}\b'

            # Function to replace matched signal with new port name, preserving bus specifiers
            def replacement_func(match):
                bus_specifier = match.group(1) if match.group(1) else ''
                return new_port + bus_specifier

            # Replace occurrences of the internal signal with the new port name, preserving bus specifiers
            parent_def = re.sub(pattern, replacement_func, parent_def)
        
        # Update the module definition in the class dictionary
        self.module_definitions[parent_module] = parent_def

    def _remove_internal_signals(self, parent_module, internal_signals):
        # Precompile a regex pattern to match bus suffixes in signal names
        bus_suffix_pattern = re.compile(r'(\[\d+:\d+\])$')

        for signal in internal_signals:
            # Remove bus suffix from signal name, if present
            signal_without_bus_suffix = bus_suffix_pattern.sub('', signal)
            
            # Attempt to remove the signal, now without its bus suffix
            if signal_without_bus_suffix in self.internal_sigs.get(parent_module, []):
                self.internal_sigs[parent_module].remove(signal_without_bus_suffix)


    def _remove_register_instance(self, parent_module, instance_name):
        # Updated pattern to match the entire instance statement, including the module name
        pattern = rf'(\w+\s+)?(?:#\s*\(\s*\.(?:.*?)\)\s*)?\s*{re.escape(instance_name)}\s*\((.*?)\);\s*'
        self.module_definitions[parent_module] = re.sub(pattern, '', self.module_definitions[parent_module], flags=re.DOTALL)

    def replace_internal_sig(self, assignment:str, sub_assignment:str,sig:str):
        if sub_assignment == "DNT" or sub_assignment == "UD":
            updated_assignment = re.sub(r'\b' + re.escape(sig) + r'\b', self.hierarchy, assignment)
            return updated_assignment
        
        # Parse the LHS and RHS from the sub_assignment
        lhs_sub, rhs_sub = sub_assignment.split('=', 1)
        lhs_sub = lhs_sub.strip()
        rhs_sub = rhs_sub.strip()

        # Pattern to find and replace the internal signal in the original assignment
        # We use a word boundary (\b) around the lhs_sub to ensure we match the whole signal name
        pattern = rf'\b{re.escape(lhs_sub)}\b'
        
        # Replace occurrences of the internal signal with its traced expression in the assignment
        # This assumes 'assignment' is the original expression where the internal signal needs to be replaced
        updated_assignment = re.sub(pattern, f'({rhs_sub[:-1]})', assignment)

        return updated_assignment

    def trace_sig( self, module_name:str, sig_name:str) :
                 
        if not self.module_definitions.get(module_name) :
            if (module_name == self.module_to_trace):
                raise ValueError(f"Module definition for '{module_name}' not found.")
        
            if module_name not in self.dont_trace_modules and not (sig_name in self.output_ports[module_name] or sig_name in self.internal_sigs[module_name] ) :
                raise ValueError(f"{sig_name} is not a port/signal of {module_name}.")
        
        assignment = self.get_assignment_statement( module_name, sig_name )
        
        self.identify_and_update_register_instance(module_name)

        if assignment is None :
            
            mod, inst, port = self.trace_output_source( module_name, sig_name )
            if mod == "UD" :
                assignment = "UD"
            else :               
                raw_assignment = self.trace_sig( mod, port )
                assignment = self.map_ports( module_name, inst, raw_assignment ) # go from ports to this module's internal sigs, or ports       
            

        
        int_sigs_to_trace = self.find_internal_signals_in_expression( module_name, assignment )
        
        while( int_sigs_to_trace ) : # keep processing until
            for sig in int_sigs_to_trace :
                sub_assignment = self.trace_sig( module_name, sig )
                
                assignment = self.replace_internal_sig( assignment, sub_assignment,sig)
                
            int_sigs_to_trace = self.find_internal_signals_in_expression( module_name, assignment )
            
        source_assignment = tracer.trace_params(module_name,assignment)
        
        return source_assignment

    def trace_params(self, module_name, expression):
        imported_packages = re.findall(r'\bimport\s+(.*?)\s*::.+;', self.module_definitions[module_name])
        if imported_packages:
            for imported_package in imported_packages :
                if imported_package in self.parameters:
                    for param_name, param_value in self.parameters[imported_package].items():
                        expression = expression.replace(f'{param_name}', str(param_value))
                else:
                    raise ValueError(f"Imported package '{imported_package}' not found in parameters.")
        
        for param_name, param_value in self.parameters[module_name].items() :
            expression = re.sub(r'\b' + re.escape(param_name) + r'\b', param_value, expression)
            
        return expression
    
    def get_signal_expression( self, module_name:str, sig_name:str) :
        source_assignment = tracer.trace_sig(module_name, outp_to_trace )
        if source_assignment == "DNT" or source_assignment == "UD":
            return f" {outp_to_trace} = {self.hierarchy}"
        else :
            for module in self.undefined_signals.keys() :
                for ud_port, ud_hierr in self.undefined_signals[module].items()   :
                    
                    source_assignment = re.sub(r'\b' + re.escape(ud_port) + r'\b', ud_hierr, source_assignment)
            
            return source_assignment
        
if __name__ == '__main__' :
    #import pdb
    if len(sys.argv) < 3 :
        print("Must supply folder location as arg1,")
        print("\t\t top module name as arg2,")
        print("\t\t and output signal name as arg3.")

    else :
        #pdb.set_trace()
        directory = sys.argv[1] if len(sys.argv) > 2 else ""
        module_name = sys.argv[2] if len(sys.argv) > 2 else ""
        outp_to_trace = sys.argv[3] if len(sys.argv) > 2 else ""
        tracer = PortTracer(directory,module_name, outp_to_trace)
        source_assignment = tracer.get_signal_expression(module_name, outp_to_trace )
        print(f"Definiton of port {outp_to_trace} of module {module_name}:\n {source_assignment}")
