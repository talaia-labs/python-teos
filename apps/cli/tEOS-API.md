## tEOS-API

### Disclaimer: Everything in here is experimental and subject to change.

The Eye of Satoshi's REST API consists, currently, of two endpoints: `/` and `/get_appointment`

`/` is the default endpoint, and is where the appointments should be sent to. `/` accepts `HTTP POST` requests only, with json request body, where data must match the following format:

	{"locator": l, "start_time": s, "end_time": e, 
	"to_self_delay": d, "encrypted_blob": eb}
	
We'll discuss the parameters one by one in the following: 
	
The locator, `l`, is the first half of the **dispute transaction id** (i.e. the 16 MSB of the dispute_txid encoded in hex). `type(l) = hex encoded str`

The start\_time, `s`, is the time when the tower will start watching your transaction, and will normally match with whenever you will be offline. `s` is measured in block height, and must be **higher than the current block height**. `type(s) = int`

The end\_time, `e`, is the time where the tower will stop watching your transaction, and will normally match with whenever you should be back online. `e` is also measured in block height, and must be **higher than** `s`. `type(e) = int`

The to\_self\_delay, `d`, is the time  the tower would have to respond with the **penalty transaction** once the **dispute transaction** is seen in the blockchain. `d` must match with the `OP_CSV` specified in the dispute transaction. If the dispute_delta does not match the `OP_CSV `, the tower would try to respond with the penalty transaction anyway, but success is not guaranteed. `d` is measured in blocks and should be, at least, `20`. `type(d) = int`

The encrypted\_blob, `eb`, is a data blob containing the `raw penalty transaction` and it is encrypted using `CHACHA20-POLY1305`. The `encryption key` used by the cipher is the sha256 of the **dispute transaction id**, and the `nonce` is a 12-byte long zero byte array:

	sk = sha256(unhexlify(secret)).digest()
	nonce = bytearray(12) # b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
	
Finally, the encrypted blob must be hex encoded. `type(eb) = hex encoded str`

The API will return a `application/json` HTTP response code `200/OK` if the appointment is accepted, with the locator encoded in the response text, or a `400/Bad Request` if the appointment is rejected, with the rejection reason encoded in the response text.

### Alpha release restrictions
The alpha release does not have authentication, payments nor rate limiting, therefore some self imposed restrictions apply:

- `start_time` should be within the next 6 blocks `[current_time+1, current_time+6]`.
- `end_time` cannot be bigger than (roughtly) a month. That is `4320` blocks on top of `start_time`.
- `encrypted_blob`s are limited to `2 kib`. 

#### Appointment example

	{"locator": "3c3375883f01027e5ca14f9760a8b853824ca4ebc0258c00e7fae4bae2571a80", 
	"start_time": 1568118, 
	"end_time": 1568120, 
	"to_self_delay": 20, 
	"encrypted_blob": "6c7687a97e874363e1c2b9a08386125e09ea000a9b4330feb33a5c698265f3565c267554e6fdd7b0544ced026aaab73c255bcc97c18eb9fa704d9cc5f1c83adaf921de7ba62b2b6ddb1bda7775288019ec3708642e738eddc22882abf5b3f4e34ef2d4077ed23e135f7fe22caaec845982918e7df4a3f949cadd2d3e7c541b1dbf77daf64e7ed61531aaa487b468581b5aa7b1da81e2617e351c9d5cf445e3391c3fea4497aaa7ad286552759791b9caa5e4c055d1b38adfceddb1ef2b99e3b467dd0b0b13ce863c1bf6b6f24543c30d"}
	
# Get appointment
	
`/get_appointment` is an endpoint provided to check the status of the appointments sent to the tower. The endpoint is accessible without any type of authentication for now. `/get_appointment` accepts `HTTP GET` requests only, where the data to be provided must be the **locator** of an appointment. The query must match the following format:

`https://teos_server:teos_port/get_appointment?locator=appointment_locator`

**Appointment can be in three states**:

- `not_found`: meaning the locator is not recognised by the API. This could either mean the locator is wrong, or the appointment has already been fulfilled.
- `being_watched`: the appointment has been accepted by the tower server and it's being watched at the moment. This stage means that the dispute transaction has not been seen yet, and therefore no penalty transaction has been published.
- `dispute_responded`: the dispute was found by the watcher and the corresponding penalty transaction has been broadcast by the node. In this stage the tower is actively monitoring until the penalty transaction reaches enough confirmations and making sure no fork occurs in the meantime.

### Get appointment response formats

`/get_appointment` will always reply with `json` containing the information about the requested appointment. The structure is as follows:

**not_found**

	[{"locator": appointment_locator, 
	"status":"not_found"}]
	
**being_watched**

	[{"encrypted_blob": eb,
	"end_time": e,
	"locator": appointment_locator,
	"start_time": s,
	"status": "being_watched",
	"to_self_delay": d}]
	
**dispute_responded**

	[{"appointment_end": e,
	"dispute_txid": dispute_txid,
	"locator": appointment_locator,
	"penalty_rawtx": penalty_rawtx,
	"penalty_txid": penalty_txid,
	"status": "dispute_responded"}]
	
Notice that the response json always contains a list. Why? It is possible for both parties to send the “same locator” to our service: 

Alice wants to hire us to watch Bob’s commitment transaction.
Bob wants to front-run Alice by creating a job for his “commitment transaction” with a bad encrypted blob.  

In the above scenario, Bob can hire our service with a bad encrypted blob for the locator that should be used by Alice. Our service will try to decrypt both encrypted blobs, find the valid transaction and send it out. More generally, this potential DoS attack is possible of locators are publicly known (i.e. other watching services). 

### Data persistence

The Eye of Satoshi keeps track of the appointment while they are being monitored, but data is wiped once an appointment has been completed with enough confirmations. Notice that during the alpha there will be no authentication, so data may be wiped periodically.


