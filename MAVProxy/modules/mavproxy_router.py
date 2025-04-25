#!/usr/bin/env python
'''enable/disable and configure a mavproxy router'''
''' TO USE:
    router create      # create the router, not started
    router delete      # delete the router and stop it
    router load my_router      # load the router named my_router.py. To load it, you must create a dict named router_config in the file,
                                and place it in the MAVProxy/router_config folder.
    
    router show      # show the whole configuration
    router show 10.11.12.13:14550      # show the whole sub-configuration related to 10.11.12.13:14550
    router show 10.11.12.13:14550 5      # show msg_types accepted from srcSystem 5
    router show 10.11.12.13:14550 5 HEARTBEAT      # show True if HEARTBEAT is accepted from srcSystem 5, False otherwise
    
    router clear      # clear the whole router
    router clear 10.11.12.13:14550      # clear the config related to 10.11.12.13:14550
    router clear 10.11.12.13:14550 4      # clear msg_types accepted from srcSystem 4
    
    router add 10.11.12.13:14550      # add an address to the router
    router add 10.11.12.13:14550 1      # add a srcSystem to the config related to 10.11.12.13:14550
    router add 10.11.12.13:14550 1 HEARTBEAT GLOBAL_POSITION_INT      # add msg_types accepted from srcSystem 1
    
    router remove 10.11.12.13:14550      # remove an address from the router
    router remove 10.11.12.13:14550 1      # remove a srcSystem from the config related to 10.11.12.13:14550
    router remove 10.11.12.13:14550 1 HEARTBEAT GLOBAL_POSITION_INT      # remove msg_types accepted from srcSystem 1
    
    router set 10.11.12.13:14550 3 HEARTBEAT GLOBAL_POSITION_INT ATTITUDE      # set msg_types accepted from srcSystem 3
    
    router start      # start the router
    router stop      # stop the router
'''
''' NOTES:
    -in address or srcSystem field, you can put other, meaning that every address/srcSystem that isn't mentionned is linked to this one.
    -in msg_types field, you can put:
        a str: meaning that only this msg_type from srcSystem can be forwarded to this address;
        a list of str: meaning that only those msg_types from srcSystem can be forwarded to this address;
        None: meaning that no message from srcSystem can be forwarded to this address;
        "all": meaning that every message from srcSystem can be forwarded to this address;
        "all/MSG_TYPE1,MSG_TYPE2": meaning that every message except MSG_TYPE1 and MSG_TYPE2 from srcSystem can be forwarded to this address.
'''

from MAVProxy.modules.lib import mp_module

try:
    import importlib
except (ImportError, ModuleNotFoundError):
    pass


class FilterOut:
    def __init__(self):
        self.allow_all = False  # If True, all values are allowed except exceptions; if False, only listed values are allowed
        self.exceptions = []  # List of exceptions from the rule above
    
    def add(self, values: str | list):
        """Adds values to the allowed list."""
        if isinstance(values, list):
            for value in values:
                self.add(value)
            return
        
        if values is None or values == "None":
            return
        
        if values == "all": # We add everything
            self.allow_all = True
            self.exceptions = []
        
        elif values.startswith("all/") and len(values) > 4: # We add everything except some
            excluded_values = values[4:].split(",") # Every msg_types that aren't added
            if self.allow_all: # Exceptions = msg_types not forwarded
                for val in self.exceptions:
                    if val not in excluded_values:
                        self.exceptions.remove(val)
            else: # Exceptions = msg_types forwarded
                self.allow_all = True
                exceptions = []
                for val in excluded_values:
                    if val not in self.exceptions:
                        exceptions.append(val)
                self.exceptions = []
                for val in exceptions:
                    if val not in self.exceptions:
                        self.exceptions.append(val)
        
        else: # We add only one thing
            if self.allow_all: # Exceptions = msg_types not forwarded
                if values in self.exceptions:
                    self.exceptions.remove(values)
            else: # Exceptions = msg_types forwarded
                if values not in self.exceptions:
                    self.exceptions.append(values)
    
    def remove(self, values: str | list):
        """Removes values from the allowed list."""
        if isinstance(values, list):
            for value in values:
                self.remove(value)
            return
        
        if values is None or values == "None":
            return
        
        if values == "all": # We remove everything
            self.allow_all = False
            self.exceptions = []
        
        elif values.startswith("all/") and len(values) > 4: # We remove everything except some
            accepted_values = values[4:].split(",") # Every msg_types that are added
            if not self.allow_all: # Exceptions = msg_types forwarded
                for val in self.exceptions:
                    if val not in accepted_values:
                        self.exceptions.remove(val)
            else: # Exceptions = msg_types not forwarded
                self.allow_all = False
                exceptions = []
                for val in accepted_values:
                    if val not in self.exceptions:
                        exceptions.append(val)
                self.exceptions = []
                for val in exceptions:
                    if val not in self.exceptions:
                        self.exceptions.append(val)
        
        else: # We remove only one thing
            if not self.allow_all: # Exceptions = msg_types forwarded
                if values in self.exceptions:
                    self.exceptions.remove(values)
            else: # Exceptions = msg_types not forwarded
                if values not in self.exceptions:
                    self.exceptions.append(values)
    
    def set(self, values: str | list | None):
        """Explicitly sets the allowed values."""
        if values is None or values == "None":
            self.allow_all = False
            self.exceptions = []
        elif isinstance(values, str):
            if values == "all":
                self.allow_all = True
                self.exceptions = []
            elif values.startswith("all/") and len(values) > 4:
                self.allow_all = True
                self.exceptions = values[4:].split(",")
            else:
                self.allow_all = False
                self.exceptions = [values]
        elif isinstance(values, list):
            self.allow_all = False
            self.exceptions = values
    
    def check(self, msg_type):
        '''check if a msg_type can be forwarded'''
        if self.allow_all:
            return msg_type not in self.exceptions
        return msg_type in self.exceptions
    
    def __repr__(self) -> str:
        """Returns a string representation of the current filter settings."""
        if self.allow_all:
            return f"all/{','.join(self.exceptions)}" if self.exceptions else "all"
        return ", ".join(self.exceptions) if self.exceptions else "None"


class RouterModule(mp_module.MPModule):
    def __init__(self, mpstate):
        super(RouterModule, self).__init__(mpstate, "router", "router control", public=True)
        self.add_command('router', self.cmd_router, "router control",
                         ["<create|delete|load|show|clear|add|remove|set|start|stop>"])
        self.router_config = None
        self.router_enabled = False

    def cmd_router(self, args):
        '''handle output commands'''
        if len(args) < 1:
            self.cmd_router_show([])
        elif args[0] == "create":
            if len(args) != 1:
                print("Usage: router create")
                return
            self.cmd_router_create()
        elif args[0] == "delete":
            if len(args) != 1:
                print("Usage: router delete")
                return
            self.cmd_router_delete()
        elif args[0] == "load":
            if len(args) != 2:
                print("Usage: router load FILE")
                return
            self.cmd_router_load(args[1:])
        elif args[0] == "show":
            if len(args) > 4:
                print("Usage 1: router show")
                print("Usage 2: router show ADDRESS")
                print("Usage 3: router show ADDRESS SRCSYSTEM")
                print("Usage 4: router show ADDRESS SRCSYSTEM MSG_TYPE")
                return
            self.cmd_router_show(args[1:])
        elif args[0] == "clear":
            if len(args) > 3:
                print("Usage 1: router clear")
                print("Usage 2: router clear ADDRESS")
                print("Usage 3: router clear ADDRESS SRCSYSTEM")
                return
            self.cmd_router_clear(args[1:])
        elif args[0] == "add":
            if len(args) == 1:
                print("Usage 1: router add ADDRESS")
                print("Usage 2: router add ADDRESS SRCSYSTEM")
                print("Usage 3: router add ADDRESS SRCSYSTEM MSG_TYPE1 MSG_TYPE2")
                return
            self.cmd_router_add(args[1:])
        elif args[0] == "remove":
            if len(args) == 1:
                print("Usage 1: router remove ADDRESS")
                print("Usage 2: router remove ADDRESS SRCSYSTEM")
                print("Usage 3: router remove ADDRESS SRCSYSTEM MSG_TYPE1 MSG_TYPE2")
                return
            self.cmd_router_remove(args[1:])
        elif args[0] == "set":
            if len(args) < 4:
                print("Usage: router set ADDRESS SRCSYSTEM MSG_TYPE1 MSG_TYPE2")
                return
            self.cmd_router_set(args[1:])
        elif args[0] == "start":
            if len(args) != 1:
                print("Usage: router start")
                return
            self.cmd_router_start()
        elif args[0] == "stop":
            if len(args) != 1:
                print("Usage: router stop")
                return
            self.cmd_router_stop()
        else:
            print("usage: router <create|delete|load|show|clear|add|remove|set|start|stop>")

    def cmd_router_create(self):
        '''initialize the router'''
        if self.router_config is None:
            self.router_config = {}
            print("Router initialized")
        else:
            print("Router already initialized")

    def cmd_router_delete(self):
        '''delete the router'''
        if self.router_enabled:
            self.router_enabled = False
        if self.router_config is not None:
            self.router_config.clear()
            self.router_config = None
        print("Router deleted")
    
    def cmd_router_load(self, args):
        '''load a router_config from a Python file'''
        self.load(args[0])
    
    def cmd_router_show(self, args):
        '''show the router_config'''
        if self.router_config is None:
            print("None")
        else:
            if len(args) == 0:
                print("{")
                for key, sub_dict in self.router_config.items():
                    print(f'    {key}: ' + '{')
                    for sub_key, value in sub_dict.items():
                        print(f'        {sub_key}: {value}')
                    print("    }")
                print("}")
            elif len(args) == 1:
                address = args[0]
                if args[0].startswith(("udp:", "tcp:")):
                    address = args[0][4:]
                if address not in self.router_config:
                    print("None")
                else:
                    print("{")
                    for sub_key, value in self.router_config[address].items():
                        print(f'    {sub_key}: {value}')
                    print("}")
            elif len(args) == 2:
                address = args[0]
                if args[0].startswith(("udp:", "tcp:")):
                    address = args[0][4:]
                if address not in self.router_config or args[1] not in self.router_config[address]:
                    print("None")
                else:
                    print(f"{self.router_config[address][args[1]]}")
            elif len(args) == 3:
                address = args[0]
                if args[0].startswith(("udp:", "tcp:")):
                    address = args[0][4:]
                if address not in self.router_config or args[1] not in self.router_config[address]:
                    print("False")
                else:
                    print(self.router_config[address][args[1]].check(args[2]))
    
    def cmd_router_clear(self, args):
        '''clear a part of the router_config'''
        if self.router_config is None:
            return
        if len(args) == 0:
            self.router_config.clear()
        elif len(args) == 1:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address in self.router_config:
                self.router_config[address].clear()
        elif len(args) == 2:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address in self.router_config and args[1] in self.router_config[address]:
                self.router_config[address][args[1]].set(None)
    
    def cmd_router_add(self, args):
        '''add a part of the router_config'''
        if self.router_config is None:
            self.router_config = {}
        if len(args) > 0:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address not in self.router_config:
                self.router_config[address] = {}
        if len(args) > 1:
            if args[1] not in self.router_config[address]:
                self.router_config[address][args[1]] = FilterOut()
        if len(args) > 2:
            self.router_config[address][args[1]].add(args[2:])
    
    def cmd_router_remove(self, args):
        '''remove a part of the router_config'''
        if self.router_config is None:
            return
        if len(args) == 0:
            self.router_config.clear()
        elif len(args) == 1:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address in self.router_config:
                self.router_config.pop(address)
        elif len(args) == 2:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address in self.router_config and args[1] in self.router_config[address]:
                self.router_config[address].pop(args[1])
        else:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address in self.router_config and args[1] in self.router_config[address]:
                self.router_config[address][args[1]].remove(args[2:])
    
    def cmd_router_set(self, args):
        '''set a part of the router_config'''
        if self.router_config is None:
            self.router_config = {}
        if len(args) > 0:
            address = args[0]
            if args[0].startswith(("udp:", "tcp:")):
                address = args[0][4:]
            if address not in self.router_config:
                self.router_config[address] = {}
        if len(args) > 1:
            if args[1] not in self.router_config[address]:
                self.router_config[address][args[1]] = FilterOut()
        if len(args) > 2:
            self.router_config[address][args[1]].set(args[2:])

    def cmd_router_start(self):
        '''start the router'''
        if self.router_config is None:
            print("Impossible to start router: router_config is None")
        else:
            if not self.router_enabled:
                self.router_enabled = True
                print("Router started")
            else:
                print("Router already started")
    
    def cmd_router_stop(self):
        '''stop the router'''
        if self.router_enabled:
            self.router_enabled = False
            print("Router stopped")
        else:
            print("Router already stopped")

    def load(self, filename):
        '''load a router_config from a Python file'''
        try:
            router_config_raw = importlib.import_module("MAVProxy.router_config.%s" % filename).router_config.copy()
        except Exception:
            try:
                router_config_raw = __import__("MAVProxy.router_config.%s" % filename).router_config.copy()
            except Exception:
                print("Error while loading %s" % filename)
                return False
        try:
            router_config = {}
            if not isinstance(router_config_raw, dict):
                raise ValueError("router_config isn't a dict")
            for address, subconfig in router_config_raw.items():
                if not isinstance(address, str):
                    raise ValueError(f'{address} is not a str')
                if address.startswith(("udp:", "tcp:")):
                    address = address[4:]
                router_config[address] = {}
                if not isinstance(subconfig, dict):
                    raise ValueError(f'{subconfig} is not a dict')
                for srcSystem, filterout in subconfig.items():
                    if not isinstance(srcSystem, (int, str)):
                        raise ValueError(f'{srcSystem} is not a int or a str')
                    router_config[address][str(srcSystem)] = FilterOut()
                    if filterout is not None and not isinstance(filterout, str) and not isinstance(filterout, list):
                        raise ValueError(f'{filterout} is not None, a str or a list')
                    router_config[address][str(srcSystem)].set(filterout)
            self.router_config = router_config
            print("Router sucessfully loaded")
            return True
        except Exception as e:
            print(f"Error while generating configuration: {e}")
            return False
    
    def start(self):
        if self.router_config is not None:
            self.router_enabled = True
            print("Router started")
    
    def check(self, msg, address):
        try:
            if not self.router_enabled:
                return True
            
            if self.router_config is None:
                return False
            
            if address in self.router_config:
                address_to_use = address
            elif "other" in self.router_config:
                address_to_use = "other"
            else:
                return False
            
            if str(msg.get_srcSystem()) in self.router_config[address_to_use]:
                srcSystem = str(msg.get_srcSystem())
            elif "other" in self.router_config[address_to_use]:
                srcSystem = "other"
            else:
                return False
            
            return self.router_config[address_to_use][srcSystem].check(msg.get_type())
        except Exception:
            return False

def init(mpstate):
    '''initialise module'''
    return RouterModule(mpstate)
