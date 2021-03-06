"""
Modbus Device Controller
-------------------------

These are the device management handlers.  They should be
maintained in the server context and the various methods
should be inserted in the correct locations.
"""
from itertools import izip
from pymodbus.interfaces import Singleton
from pymodbus.utilities import dict_property

#---------------------------------------------------------------------------#
# Network Access Control
#---------------------------------------------------------------------------#
class ModbusAccessControl(Singleton):
    '''
    This is a simple implementation of a Network Management System table.
    Its purpose is to control access to the server (if it is used).
    We assume that if an entry is in the table, it is allowed accesses to
    resources.  However, if the host does not appear in the table (all
    unknown hosts) its connection will simply be closed.

    Since it is a singleton, only one version can possible exist and all
    instances pull from here.
    '''
    __nmstable = [
            "127.0.0.1",
    ]

    def __iter__(self):
        ''' Iterater over the network access table

        :returns: An iterator of the network access table
        '''
        return self.__nmstable.__iter__()

    def add(self, host):
        ''' Add allowed host(s) from the NMS table

        :param host: The host to add
        '''
        if not isinstance(host, list):
            host = [host]
        for entry in host:
            if entry not in self.__nmstable:
                self.__nmstable.append(entry)

    def remove(self, host):
        ''' Remove allowed host(s) from the NMS table

        :param host: The host to remove
        '''
        if not isinstance(host, list):
            host = [host]
        for entry in host:
            if entry in self.__nmstable:
                self.__nmstable.remove(entry)

    def check(self, host):
        ''' Check if a host is allowed to access resources

        :param host: The host to check
        '''
        return host in self.__nmstable

#---------------------------------------------------------------------------#
# Device Information Control
#---------------------------------------------------------------------------#
class ModbusDeviceIdentification(object):
    '''
    This is used to supply the device identification
    for the readDeviceIdentification function

    For more information read section 6.21 of the modbus
    application protocol.
    '''
    __data = {
        0x00: '', # VendorName
        0x01: '', # ProductCode
        0x02: '', # MajorMinorRevision
        0x03: '', # VendorUrl
        0x04: '', # ProductName
        0x05: '', # ModelName
        0x06: '', # UserApplicationName
        0x07: '', # reserved
        0x08: '', # reserved
        # 0x80 -> 0xFF are private
    }

    __names = [
        'VendorName',
        'ProductCode',
        'MajorMinorRevision',
        'VendorUrl',
        'ProductName',
        'ModelName',
        'UserApplicationName',
    ]

    def __init__(self, info=None):
        '''
        Initialize the datastore with the elements you need.
        (note acceptable range is [0x00-0x06,0x80-0xFF] inclusive)

        :param info: A dictionary of {int:string} of values
        '''
        if isinstance(info, dict):
            for key in info.keys():
                if (0x06 >= key >= 0x00) or (0x80 > key > 0x08):
                    self.__data[key] = info[key]

    def __iter__(self):
        ''' Iterater over the device information

        :returns: An iterator of the device information
        '''
        return self.__data.iteritems()

    def summary(self):
        ''' Return a summary of the main items

        :returns: An dictionary of the main items
        '''
        return dict(zip(self.__names, self.__data.itervalues()))

    def update(self, input):
        ''' Update the values of this identity
        using another identify as the value

        :param input: The value to copy values from
        '''
        self.__data.update(input)

    def __setitem__(self, key, value):
        ''' Wrapper used to access the device information

        :param key: The register to set
        :param value: The new value for referenced register
        '''
        if key not in [0x07, 0x08]:
            self.__data[key] = value

    def __getitem__(self, key):
        ''' Wrapper used to access the device information

        :param key: The register to read
        '''
        return self.__data.setdefault(key, '')

    def __str__(self):
        ''' Build a representation of the device

        :returns: A string representation of the device
        '''
        return "DeviceIdentity"

    #---------------------------------------------------------------------------#
    # Properties
    #---------------------------------------------------------------------------#
    VendorName          = dict_property(lambda s: s.__data, 0)
    ProductCode         = dict_property(lambda s: s.__data, 1)
    MajorMinorRevision  = dict_property(lambda s: s.__data, 2)
    VendorUrl           = dict_property(lambda s: s.__data, 3)
    ProductName         = dict_property(lambda s: s.__data, 4)
    ModelName           = dict_property(lambda s: s.__data, 5)
    UserApplicationName = dict_property(lambda s: s.__data, 6)

#---------------------------------------------------------------------------#
# Counters Handler
#---------------------------------------------------------------------------#
class ModbusCountersHandler(object):
    '''
    This is a helper class to simplify the properties for the counters::

    0x0B  1  Return Bus Message Count

             Quantity of messages that the remote
             device has detected on the communications system since its
             last restart, clear counters operation, or power-up.  Messages
             with bad CRC are not taken into account. 

    0x0C  2  Return Bus Communication Error Count 

             Quantity of CRC errors encountered by the remote device since its last 
             restart, clear counters operation, or power-up.  In case of an error 
             detected on the character level, (overrun, parity error), or in case of a 
             message length < 3 bytes, the receiving device is not able to calculate 
             the CRC.  In such cases, this counter is also incremented. 

    0x0D  3  Return Slave Exception Error Count

             Quantity of MODBUS exception error detected by the remote device 
             since its last restart, clear counters operation, or power-up.  It 
             comprises also the error detected in broadcast messages even if an 
             exception message is not returned in this case.  
             Exception errors are described and listed in "MODBUS Application 
             Protocol Specification" document. 

    0xOE  4  Return Slave Message Count

             Quantity of messages addressed to the remote device,  including 
             broadcast messages, that the remote device has processed since its 
             last restart, clear counters operation, or power-up. 

    0x0F  5  Return Slave No Response Count 
             Quantity of messages received by the remote device for which it 
             returned no response (neither a normal response nor an exception 
             response), since its last restart, clear counters operation, or power-up.  
             Then, this counter counts the number of broadcast messages it has 
             received.

    0x10  6  Return Slave NAK Count

             Quantity of messages addressed to the remote device for which it 
             returned a Negative Acknowledge (NAK) exception response, since its 
             last restart, clear counters operation, or power-up. Exception 
             responses are described and listed in "MODBUS Application Protocol 
             Specification" document. 

    0x11  7  Return Slave Busy Count

             Quantity of messages addressed to the remote device for which it 
             returned a Slave Device Busy exception response, since its last restart, 
             clear counters operation, or power-up. Exception responses are 
             described and listed in "MODBUS Application Protocol Specification" 
             document

    0x12  8  Return Bus Character Overrun Count

             Quantity of messages addressed to the remote device that it could not
             handle due to a character overrun condition, since its last restart, clear
             counters operation, or power-up. A character overrun is caused by data 
             characters arriving at the port faster than they can 

    .. note:: I threw the event counter in here for convinience
    '''
    __data = dict([(i, 0x0000) for i in range(9)])
    __names   = [
        'BusMessage',
        'BusCommunicationError',
        'SlaveExceptionError',
        'SlaveMessage',
        'SlaveNoResponse',
        'SlaveNAK',
        'SlaveBusy',
        'BusCharacterOverrun'
        'Event '
    ]

    def __iter__(self):
        ''' Iterater over the device counters

        :returns: An iterator of the device counters
        '''
        return izip(self.__names, self.__data.itervalues())

    def update(self, input):
        ''' Update the values of this identity
        using another identify as the value

        :param input: The value to copy values from
        '''
        for k,v in input.iteritems():
            v += self.__getattribute__(k)
            self.__setattr__(k,v)

    def reset(self):
        ''' This clears all of the system counters
        '''
        self.__data = dict([(i, 0x0000) for i in range(9)])

    def summary(self):
        ''' Returns a summary of the counters current status

        :returns: A byte with each bit representing each counter
        '''
        count, result = 0x01, 0x00
        for i in self.__data.values():
            if i != 0x00: result |= count
            count <<= 1
        return result

    #---------------------------------------------------------------------------#
    # Properties
    #---------------------------------------------------------------------------#
    BusMessage            = dict_property(lambda s: s.__data, 0)
    BusCommunicationError = dict_property(lambda s: s.__data, 1)
    BusExceptionError     = dict_property(lambda s: s.__data, 2)
    SlaveMessage          = dict_property(lambda s: s.__data, 3)
    SlaveNoResponse       = dict_property(lambda s: s.__data, 4)
    SlaveNAK              = dict_property(lambda s: s.__data, 5)
    SlaveBusy             = dict_property(lambda s: s.__data, 6)
    BusCharacterOverrun   = dict_property(lambda s: s.__data, 7)
    Event                 = dict_property(lambda s: s.__data, 8)

#---------------------------------------------------------------------------#
# Main server controll block
#---------------------------------------------------------------------------#
class ModbusControlBlock(Singleton):
    '''
    This is a global singleotn that controls all system information

    All activity should be logged here and all diagnostic requests
    should come from here.
    '''

    __mode = 'ASCII'
    __diagnostic = [False] * 16
    __instance = None
    __listen_only = False
    __delimiter = '\r'
    __counters = ModbusCountersHandler()
    __identity = ModbusDeviceIdentification()
    __events   = []

    #---------------------------------------------------------------------------#
    # Magic
    #---------------------------------------------------------------------------#
    def __str__(self):
        ''' Build a representation of the control block

        :returns: A string representation of the control block
        '''
        return "ModbusControl"

    def __iter__(self):
        ''' Iterater over the device counters

        :returns: An iterator of the device counters
        '''
        return self.__counters.__iter__()

    #---------------------------------------------------------------------------#
    # Events
    #---------------------------------------------------------------------------#
    def addEvent(self, event):
        ''' Adds a new event to the event log

        :param event: A new event to add to the log
        '''
        self.__events.insert(0, event)
        self.__events = self.__events[0:64] # chomp to 64 entries
        self.Counter.Event += 1

    def getEvents(self):
        ''' Returns an encoded collection of the event log.

        :returns: The encoded events packet
        '''
        events = [event.encode() for event in self.__events]
        return ''.join(events)

    def clearEvents(self):
        ''' Clears the current list of events
        '''
        self.__events = []

    #---------------------------------------------------------------------------#
    # Other Properties
    #---------------------------------------------------------------------------#
    Identity = property(lambda s: s.__identity)
    Counter  = property(lambda s: s.__counters)
    Events   = property(lambda s: s.__events)

    def reset(self):
        ''' This clears all of the system counters and the
            diagnostic register
        '''
        self.__events = []
        self.__counters.reset()
        self.__diagnostic = [False] * 16

    #---------------------------------------------------------------------------#
    # Listen Properties
    #---------------------------------------------------------------------------#
    def _setListenOnly(self, value):
        ''' This toggles the listen only status

        :param value: The value to set the listen status to
        '''
        self.__listen_only = value is not None

    ListenOnly = property(lambda s: s.__listen_only, _setListenOnly)

    #---------------------------------------------------------------------------#
    # Mode Properties
    #---------------------------------------------------------------------------#
    def _setMode(self, mode):
        ''' This toggles the current serial mode

        :param mode: The data transfer method in (RTU, ASCII)
        '''
        if mode in ['ASCII', 'RTU']:
            self.__mode = mode

    Mode = property(lambda s: s.__mode, _setMode)

    #---------------------------------------------------------------------------#
    # Delimiter Properties
    #---------------------------------------------------------------------------#
    def _setDelimiter(self, char):
        ''' This changes the serial delimiter character

        :param char: The new serial delimiter character
        '''
        if isinstance(char, str):
            self.__delimiter = char
        elif isinstance(char, int):
            self.__delimiter = chr(char)

    Delimiter = property(lambda s: s.__delimiter, _setDelimiter)

    #---------------------------------------------------------------------------#
    # Diagnostic Properties
    #---------------------------------------------------------------------------#
    def setDiagnostic(self, mapping):
        ''' This sets the value in the diagnostic register

        :param mapping: Dictionary of key:value pairs to set
        '''
        for entry in mapping.iteritems():
            if entry[0] >= 0 and entry[0] < len(self.__diagnostic):
                self.__diagnostic[entry[0]] = (entry[1] != 0)

    def getDiagnostic(self, bit):
        ''' This gets the value in the diagnostic register

        :param bit: The bit to get
        :returns: The current value of the requested bit
        '''
        if bit >= 0 and bit < len(self.__diagnostic):
            return self.__diagnostic[bit]
        return None

    def getDiagnosticRegister(self):
        ''' This gets the entire diagnostic register

        :returns: The diagnostic register collection
        '''
        return self.__diagnostic

#---------------------------------------------------------------------------# 
# Exported Identifiers
#---------------------------------------------------------------------------# 
__all__ = [
        "ModbusAccessControl",
        "ModbusDeviceIdentification",
        "ModbusControlBlock"
]
