# WLED brightness API notes

Source: https://kno.wled.ge/interfaces/json-api/

GET /json/info returns an object with brand (the string WLED for a standard build),
mac (persistent controller identifier) and name (user-facing name).
GET /json/state returns integer bri on a 0..255 scale and boolean on. When off,
bri retains the last lit brightness. POST a JSON object to /json/state to change
state. To switch off send on=false. To set a positive brightness send on=true
and the new bri. Perform a fresh GET after writing to confirm the actual state.

GhostUI should expose only brightness, labelled Brightness, with an integer range
of 0..100. Zero means off. Use the controller MAC to distinguish individual rings.
