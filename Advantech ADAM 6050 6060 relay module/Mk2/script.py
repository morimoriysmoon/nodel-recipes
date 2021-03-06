'''Lightweight modbus control.'''

# REVISION HISTORY
# 21-Jan-2018 
#   Support for read-only unsigned 16-bit MODBUS registers (use Custom)
#
# 20-Jan-2018  (minor, non-functional)
#   Uses the 'request_queue' from the toolkit to manually handle any packet fragmentation that is possible with
#   MODBUS' length-delimeted packetised stream over TCP. This is very unlikely when direct from Advantech MODBUS hardware
#   but possible when port-forwarding.

TCP_PORT = 502

DEFAULT_BOUNCE = 1.2 # the default bounce time (1200 ms)

param_ipAddress = Parameter({ "title":"IP address", "order": next_seq(), "schema": { "type":"string" },
                              "desc": "The IP address of the unit."})

CUSTOM = 'Custom'
ADAM_6050 = 'Advantech ADAM 6050 (12xDI 6xDO)'
ADAM_6060 = 'Advantech ADAM 6060 (6xDI 6xrelay)'

DEVICE_CONFIGS = { ADAM_6050: { 'coils':
                                 [ {'startAddr': 0, 'count': 12, 'prefix': 'Input', 'readOnly': True},
                                   {'startAddr': 16, 'count': 6, 'prefix': 'Output', 'readOnly': False} ],
                                'registers': []
                              },
                   ADAM_6060: { 'coils': 
                                 [ {'startAddr': 0, 'count': 6, 'prefix': 'Input', 'readOnly': True},
                                   {'startAddr': 16, 'count': 6, 'prefix': 'Relay', 'readOnly': False} ],
                                'registers': []
                              }
                 }

param_modbusDevice = Parameter({'title': 'Modbus device', 'order': next_seq(), 'schema': {'type': 'string', 'enum': [CUSTOM, ADAM_6050, ADAM_6060]}})

param_coilBanks = Parameter({ 'title': 'Custom coil banks', 'order': next_seq(), 'schema': { 'type': 'array', 'items': {
        'type': 'object', 'properties': {
          'startAddr': {'type': 'integer', 'title': 'Start address', 'order': next_seq()},
          'count': {'type': 'integer', 'title': 'Count', 'order': next_seq()},
          'prefix': {'type': 'string', 'title': 'Prefix', 'order': next_seq(), 'desc': 'e.g "Input" or "Output"'},
          'readOnly': {'type': 'boolean', 'title': 'Read-only?', 'order': next_seq()}
    } } } })

param_registerBanks = Parameter({ 'title': 'Custom register banks', 'order': next_seq(), 'schema': { 'type': 'array', 'items': {
        'type': 'object', 'properties': {
          'startAddr': {'type': 'integer', 'title': 'Start address', 'order': next_seq()},
          'count': {'type': 'integer', 'title': 'Count', 'order': next_seq()},
          'prefix': {'type': 'string', 'title': 'Prefix', 'order': next_seq(), 'desc': 'e.g "Input" or "Output"'},
          'readOnly': {'type': 'boolean', 'title': '(RESERVED) Read-only? (only read-only for now)', 'order': next_seq()}
    } } } })

local_event_SyncErrors = LocalEvent({'title': 'Sync errors', 'group': 'Status', 'schema': {'type': 'object', 'title': 'Details', 'properties': {
        'count': {'type': 'integer', 'title': 'Count', 'order': 1},
		'last': {'type': 'string', 'title': 'Last occurrence', 'order': 2}
		}}})

local_event_ShowLog = LocalEvent({'title': 'Show log', 'order': 9998, 'group': 'Debug', 'schema': {'type': 'boolean'}})

# hold the list of poller functions
pollers = list()

def main(arg = None):
  tcp.setDest('%s:%s'% (param_ipAddress, TCP_PORT))
  
  # lookup the config based on the device
  deviceConfig = DEVICE_CONFIGS.get(param_modbusDevice)
  
  if deviceConfig != None:
    for info in deviceConfig.get('coils') or []:
      bindCoilBank(info)
    
    for info in deviceConfig.get('registers') or []:
      bindRegisterBank(info)
    
  else:
    # 'Custom' and everything will fallthrough to here
    for info in param_coilBanks or []:
      bindCoilBank(info)
    
    for info in param_registerBanks or []:
      bindRegisterBank(info)
    
def bindCoilBank(info):
  startAddr = info['startAddr']
  prefix = info['prefix']
  count = info['count']
  readOnly = info['readOnly']
  
  coilEvents = list()
  
  for i in range(info['count']):
    (event, configEvent) = bindCoil(prefix, i+1, startAddr+i, readOnly)
    coilEvents.append((event, configEvent))
    
  pollGap = 0.08 if readOnly else 2.0

  def onBankResponse(seqNum, values):
    for (es, v) in zip(coilEvents, values):
      invert = safeGet(es[1].getArg(), 'invert', False)
      es[0].emitIfDifferent(v if not invert else not v)
    
    call_safe(lambda: readBank(seqNum), pollGap)
    
  def readBank(seqNum):
    # chain next call (instead of locked timer)
    if seqNum != sequence[0]:
      # stop this chain
      print '(connection %s ended)' % seqNum
      return
    
    modbus_readCoils(startAddr, count, lambda values: onBankResponse(seqNum, values))
    
  pollers.append(readBank)
  
def bindCoil(prefix, index, addr, readOnly):
  event = Event('%s %s State' % (prefix, index), {'group': '"%s" coils\' states' % prefix, 'order': next_seq(), 'schema': {'type': 'boolean'}})
  configEvent = Event('%s %s Config' % (prefix, index), {'group': '"%s" coils\' config' % prefix, 'order': next_seq(), 'schema': {'type': 'object', 'title': 'Params', 'properties': {
          'invert': {'type': 'boolean', 'title': 'Invert', 'order': next_seq()},
          'label': {'type': 'string', 'title': 'Label', 'order': next_seq()}
        }}})
  
  label = safeGet(configEvent.getArg(), 'label', None)
  
  if label != None:
    event2 = Event('%s State' % label, {'group': 'Labelled coils\' states', 'order': next_seq()+8000, 'schema': {'type': 'boolean'}})
    event.addEmitHandler(lambda arg: event2.emit(arg))
  
  if not readOnly:
    def handler(arg):
      modbus_writeCoil(addr, arg, lambda state: event.emit(state))
    
    group = '%s %s coil' % (prefix, index)
    stateAction = Action('%s %s State' % (prefix, index), handler, {'title': 'State', 'group': group, 'order': next_seq(), 'schema': {'type': 'boolean'}})
    closeAction = Action('%s %s Close' % (prefix, index), lambda arg: stateAction.call(True), {'title': 'Close', 'group': group, 'order': next_seq()})
    openAction = Action('%s %s Open' % (prefix, index), lambda arg: stateAction.call(False), {'title': 'Open', 'group': group, 'order': next_seq()})
    
    timer = Timer(lambda: stateAction.call(stateAction.getArg() != True), 0)
    
    def bounceHandler(arg=None):
      stateAction.call(True)
      timer.setDelay(DEFAULT_BOUNCE)
      timer.start()
    
    bounceAction = Action('%s %s Bounce' % (prefix, index), bounceHandler, {'title': 'Bounce', 'group': group, 'order': next_seq()})

    def flashHandler(arg=None):
      stateAction.call(True)
      timer.setDelay(DEFAULT_BOUNCE)
      timer.setInterval(DEFAULT_BOUNCE)
      timer.start()
    
    flashAction = Action('%s %s Flash' % (prefix, index), lambda arg: flashHandler() if arg else timer.stop(), {'title': 'Flash', 'group': group, 'order': next_seq(), 'schema': {'type': 'boolean'}})
    
    if label != None:
      group = '%s coil' % label
      stateAction2 = Action('%s State' % label, lambda arg: stateAction.call(arg), {'title': 'State', 'group': group, 'order': next_seq()+8000, 'schema': {'type': 'boolean'}})
      closeAction2 = Action('%s Close' % label, lambda arg: closeAction.call(arg), {'title': 'Close', 'group': group, 'order': next_seq()+8000})
      openAction2 = Action('%s Open' % label, lambda arg: openAction.call(arg), {'title': 'Open', 'group': group, 'order': next_seq()+8000})
      bounceAction2 = Action('%s Bounce' % label, lambda arg: bounceAction.call(arg), {'title': 'Bounce', 'group': group, 'order': next_seq()+8000})
      flashAction2 = Action('%s Flash' % label, lambda arg: flashAction.call(arg), {'title': 'Flash', 'group': group, 'order': next_seq()+8000, 'schema': {'type': 'boolean'}})
  
  return (event, configEvent)

def bindRegisterBank(info):
  startAddr = info['startAddr']
  prefix = info['prefix']
  count = info['count']
  readOnly = True # info.get('readOnly') not used yet, would be
  
  registerEvents = list()
  
  for i in range(info['count']):
    (event, configEvent) = bindRegister(prefix, i+1, startAddr+i, readOnly)
    registerEvents.append((event, configEvent))
    
  pollGap = 0.08 if readOnly else 2.0

  def onRegisterResponse(seqNum, values):
    for (es, v) in zip(registerEvents, values):
      es[0].emitIfDifferent(v)
    
    call_safe(lambda: readRegister(seqNum), pollGap)
    
  def readRegister(seqNum):
    # chain next call (instead of locked timer)
    if seqNum != sequence[0]:
      # stop this chain
      print '(connection %s ended)' % seqNum
      return
    
    modbus_readRegisters(startAddr, count, lambda values: onRegisterResponse(seqNum, values))
    
  pollers.append(readRegister)

def bindRegister(prefix, index, addr, readOnly):
  # 'readOnly' not used yet
  event = Event('%s %s Value' % (prefix, index), {'group': '"%s" registers\' values' % prefix, 'order': next_seq(), 'schema': {'type': 'integer'}})
  configEvent = Event('%s %s Config' % (prefix, index), {'group': '"%s" registers\' config' % prefix, 'order': next_seq(), 'schema': {'type': 'object', 'title': 'Params', 'properties': {
          'label': {'type': 'string', 'title': 'Label', 'order': next_seq()}
        }}})
  
  label = safeGet(configEvent.getArg(), 'label', None)
  
  if label != None:
    event2 = Event('%s Value' % label, {'group': 'Labelled registers\' values', 'order': next_seq()+8000, 'schema': {'type': 'integer'}})
    event.addEmitHandler(lambda arg: event2.emit(arg))
  
  return (event, configEvent)

sequence = [0]

def connected():
  console.info('TCP connected')
  
  # don't let commands rush through

  tcp.clearQueue()
  queue.clearQueue()
  
  # start all the poller
  seqNum = sequence[0]
  
  console.info('(new sequence %s)' % seqNum)

  for f in pollers:
    f(seqNum)
  
def received(data):
  lastReceive[0] = system_clock()

  if local_event_ShowLog.getArg():
    print 'RECV: [%s]' % data.encode('hex')
    
  # ensure buffer doesn't blow out i.e. greater than a reasonable sized "massive" value
  if len(recvBuffer) > 4096:
    console.warn('The incoming buffer is too large which might indicate protocol corruption; dropping it')
    del recvBuffer[:]

  # extend the recv buffer
  recvBuffer.extend(data)

  processBuffer()    
  
def sent(data):
  if local_event_ShowLog.getArg():
    print 'SENT: [%s]' % data.encode('hex')
  
def disconnected():
  console.warn('TCP disconnected')
  
  # reset sequence (which will stop pollers)
  tcp.clearQueue()
  queue.clearQueue()
  
  newSeq = sequence[0] + 1
  sequence[0] = newSeq
  
def timeout():
  console.warn('TCP timeout (recycling TCP connection if connected)')
  tcp.drop()

tcp = TCP(connected=connected, 
          received=received, 
          sent=sent, 
          disconnected=disconnected, 
          timeout=timeout, 
          sendDelimiters=None, 
          receiveDelimiters=None)

def protocolTimeout():
  console.log('MODBUS timeout; flushing buffers and dropping TCP connection for good measure')
  tcp.drop()
  queue.clearQueue()
  del recvBuffer[:]

# MODBUS using no delimeters within its binary protocol so must use a 
# custom request queue
queue = request_queue(timeout=protocolTimeout)

# the full receive buffer
recvBuffer = list()

# example response packet:
# 00:93            00:00                00:05                 01:01:02:fd:0f
# TID (2 bytes)    Protocol (2 bytes)   Length, n (2 bytes)   n bytes...
def processBuffer():
  while True:
    bufferLen = len(recvBuffer)
    if bufferLen < 6:
      # not big enough yet, let it grow
      return
  
    # got at least 6 bytes (fifth and sixth hold the length)
    messageLen = toInt16(recvBuffer, 4)
  
    # work out expected length (incl. header)
    fullLen = 2 + 2 + 2 + messageLen
  
    # check if we've got at least one full packet
    if bufferLen >= fullLen:
      # grab that packet from the buffer
      message = ''.join(recvBuffer[:fullLen])
      del recvBuffer[:fullLen]
      
      # and 'push' it back through the request queue handler
      queue.handle(message)
      
      # might be more, so continue...
      
    else:
      return

# modbus ----
READ_COILS = 1
READ_REGISTERS = 3
FORCE_COIL = 5

def handleModbusResponse(resp, expTid, count=0, onFuncResp=None):
  # Response example
  # (raw buffer): 0093 0000 0005 01 01 02 fd0f
  tID = toInt16(resp, 0)
  if tID != expTid:
    handleTIDMismatch(tID, expTid)
    return

  protID = toInt16(resp, 2)
  length = toInt16(resp, 4)
    
  unit = ord(resp[6])
  modbus_func = ord(resp[7])
  byteCount = ord(resp[8])
  
  if modbus_func == READ_COILS:
    bits = list()
    
    for i in range(byteCount):
      for b in range(8):
        bits.append(isBitSet(ord(resp[9+i]), b))
        
        if len(bits) >= count:
          break
    
    if local_event_ShowLog.getArg():
      console.log('READ_COILS resp: tid:%s protID:%s len:%s unit:%s func:%s count:%s bits:%s' % (tID, protID, length, unit, modbus_func, count, ''.join(['1' if x else '0' for x in bits])))
      
    if onFuncResp:
      # return boolean array
      onFuncResp(bits)


  if modbus_func == READ_REGISTERS:
    registers = list()

    # go through the 2-byte registers which
    # starts at offset 9
    for i in range(count):
      registers.append(toInt16(resp, 9+i*2))
    
    if local_event_ShowLog.getArg():
      console.log('READ_REGISTERS resp: tid:%s protID:%s len:%s unit:%s func:%s count:%s registers:%s' % (tID, protID, length, unit, modbus_func, count, registers))
      
    if onFuncResp:
      # return boolean array
      onFuncResp(registers)


  elif modbus_func == FORCE_COIL:
    # e.g. 0001 0000 0006 01 05 0010 ff00
    
    if local_event_ShowLog.getArg():
      print 'WRITE_COIL resp: tid:%s protID:%s len:%s unit:%s func:%s' % (tID, protID, length, unit, modbus_func)
    
    if onFuncResp:
      state = resp[-2:]=='\xff\x00'
      onFuncResp(state)


def modbus_readCoils(startAddr=0, count=12, onFuncResp=None):
  # Request example:
  #      \x00\x93  \x00\x00  \x00\x06  \x01  \x01         \x00\x00     \x00\x0c                                      
  #      tID2      protID2   length2   unit  modbus_func  start_addr2  count
  (tid, protID, length, unitID, modbus_func) = (next_seq() % 65536, 0, 6, 1, READ_COILS)
  
  req = '%s%s%s%s%s%s%s' % (formatInt16(tid), formatInt16(protID), formatInt16(length),
                            chr(unitID), chr(modbus_func), formatInt16(startAddr), formatInt16(count))
  
  queue.request(lambda: tcp.send(req), lambda resp: handleModbusResponse(resp, tid, count, onFuncResp=onFuncResp))
  
Action('ReadCoils', lambda arg: modbus_readCoils(arg['startAddr'], arg['count']), 
       metadata={'group': 'Modbus', 'order': next_seq()+9000, 'schema': {'type': 'object', 'title': 'Params', 'properties': {
        'startAddr': {'type': 'integer', 'title': 'Start address', 'order': 1},
        'count': {'type': 'integer', 'title': 'Count', 'order': 2}}}})


def modbus_readRegisters(startAddr=0, count=12, onFuncResp=None):
  # Request example (read 3 registers, from address 00:6B)
  #      \x00\x93  \x00\x00  \x00\x06  \x01  \x03         \x00\x6b     \x00\x03
  #      tID2      protID2   length2   unit  modbus_func  start_addr2  count
  (tid, protID, length, unitID, modbus_func) = (next_seq() % 65536, 0, 6, 1, READ_REGISTERS)
  
  req = '%s%s%s%s%s%s%s' % (formatInt16(tid), formatInt16(protID), formatInt16(length),
                            chr(unitID), chr(modbus_func), formatInt16(startAddr), formatInt16(count))
  
  queue.request(lambda: tcp.send(req), lambda resp: handleModbusResponse(resp, tid, count, onFuncResp=onFuncResp))

Action('ReadRegisters', lambda arg: modbus_readRegisters(arg['startAddr'], arg['count']), 
       metadata={'group': 'Modbus', 'order': next_seq()+9000, 'schema': {'type': 'object', 'title': 'Params', 'properties': {
        'startAddr': {'type': 'integer', 'title': 'Start address', 'order': 1},
        'count': {'type': 'integer', 'title': 'Count', 'order': 2}}}})  

def modbus_writeCoil(addr, state, onFuncResp=None):
  # e.g 00 01     00 00     00 06     01    05           00 10     ff 00
  #     tID2      protID2   length2   unit  modbus_func  addr      state
  (tid, protID, length, unitID, modbus_func) = (next_seq() % 65536, 0, 6, 1, FORCE_COIL)
  
  if state == True:
    value = '\xff\x00'
  else:
    value = '\x00\x00'
  
  req = '%s%s%s%s%s%s%s' % (formatInt16(tid), formatInt16(protID), formatInt16(length),
                            chr(unitID), chr(modbus_func), formatInt16(addr), value)
  
  queue.request(lambda: tcp.send(req), lambda resp: handleModbusResponse(resp, tid, onFuncResp=onFuncResp))

Action('WriteCoil', lambda arg: modbus_writeCoil(arg['addr'], arg['state']), 
       metadata={'group': 'Modbus', 'order': next_seq()+9000, 'schema': {'type': 'object', 'title': 'Params', 'properties': {
        'addr': {'type': 'integer', 'title': 'Start address', 'order': 1},
        'state': {'type': 'boolean', 'title': 'State', 'order': 2}}}})           


def handleTIDMismatch(tid, expTID):
  console.warn('Mismatched TID (modbus seqnum) detected; dropping connection and resyncing... tid=%s, expected=%s' % (tid, expTID))
  
  arg = local_event_SyncErrors.getArg() or {'count': 0}
  arg['count'] = int(arg.get('count') or 0) + 1
  arg['last'] = str(date_now())
  local_event_SyncErrors.emit(arg)
                                     
  tcp.drop()
		
# convenience functions ----

def toInt16(buff, offset):
  return ord(buff[offset])*256 + ord(buff[offset+1])

def formatInt16(v):
  return '%s%s' % (chr(v/256), chr(v%256))

def isBitSet(x, offset):
  return x & (1 << offset) > 0

def safeGet(m, key, default=None):
  if m == None:
    return default
  
  v = m.get(key)
  
  if v == None:
    return default
  
  return v

  
# status  ----

local_event_Status = LocalEvent({'group': 'Status', 'order': 9990, "schema": { 'title': 'Status', 'type': 'object', 'properties': {
        'level': {'title': 'Level', 'order': next_seq(), 'type': 'integer'},
        'message': {'title': 'Message', 'order': next_seq(), 'type': 'string'}
    } } })

# for status checks
lastReceive = [0]

# roughly, the last contact  
local_event_LastContactDetect = LocalEvent({'group': 'Status', 'title': 'Last contact detect', 'schema': {'type': 'string'}})
  
def statusCheck():
  diff = (system_clock() - lastReceive[0])/1000.0 # (in secs)
  now = date_now()
  
  if diff > status_check_interval+15:
    previousContactValue = local_event_LastContactDetect.getArg()
    
    if previousContactValue == None:
      message = 'Always been missing.'
      
    else:
      previousContact = date_parse(previousContactValue)
      roughDiff = (now.getMillis() - previousContact.getMillis())/1000/60
      if roughDiff < 60:
        message = 'Missing for approx. %s mins' % roughDiff
      elif roughDiff < (60*24):
        message = 'Missing since %s' % previousContact.toString('h:mm:ss a')
      else:
        message = 'Missing since %s' % previousContact.toString('h:mm:ss a, E d-MMM')
      
    local_event_Status.emit({'level': 2, 'message': message})
    
  else:
    local_event_LastContactDetect.emit(str(now))
    local_event_Status.emit({'level': 0, 'message': 'OK'})
    
status_check_interval = 75
status_timer = Timer(statusCheck, status_check_interval)
