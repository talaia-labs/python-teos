## PISA-API

### Disclaimer: Everything in here is experimental and subject to change.

The PISA REST API consists, currently, of two endpoints: `/` and `/check_appointment`

`/` is the default endpoint, and is where the appointments should be sent to. `/` accepts `HTTP POST` requests only, with json request body, where data must match the following format:

	{"locator": l, "start_time": s, "end_time": e, 
	"dispute_delta": d, "encrypted_blob": eb, "cipher":
	c, "hash_function": h}
	
We'll discuss the parameters one by one in the following: 
	
The locator, `l`, is the `sha256` hex representation of the **dispute transaction id** (i.e. the sha256 of the byte representation of the dispute transaction id encoded in hex). `type(l) = hex encoded str`

The start\_time, `s`, is the time when the PISA server will start watching your transaction, and will normally match with whenever you will be offline. `s` is measured in block height, and must be **higher than the current block height** and not too close to it. `type(s) = int`

The end\_time, `e`, is the time where the PISA server will stop watching your transaction, and will normally match which whenever you should be back online. `e` is also measured in block height, and must be **higher than** `s`. `type(e) = int`

The dispute\_delta, `d`, is the time PISA would have to respond with the **justice transaction** once the **dispute transaction** is seen in the blockchain. `d` must match with the `OP_CSV` specified in the dispute transaction. If the dispute_delta does not match the `OP_CSV `, PISA would try to respond with the justice transaction anyway, but success is not guaranteed. `d` is measured in blocks and should be, at least, `20`. `type(d) = int`

The encrypted\_blob, `eb`, is a data blob containing the `raw justice transaction` and it is encrypted using `AES-GCM-128`. The `encryption key` and `nonce` used by the cipher are **derived from the justice transaction id** as follows:

	master_key = SHA256(tx_id|tx_id)
	sk = master_key[:16] 
	nonce = master_key[16:]
	
where `| `represents concatenation, `[:16]` represent the first half (16 bytes), and `[16:]` represents the second half of the master key. Finally, the encrypted blob must be hex encoded. `type(eb) = hex encoded str`

The cipher, `c`, represents the cipher used to encrypt `eb`. The only cipher supported, for now, is `AES-GCM-128`. `type(c) = str`

The hash\_function, `h`, represents the hash function used to derive the encryption key and the nonce used to create `eb`. The only hash function supported, for now, is `SHA256`. `type(h) = str`

The API will return a `text/plain` HTTP response code `200/OK` if the appointment is accepted, with the locator encoded in the response text, or a `400/Bad Request` if the appointment is rejected, with the rejection reason encoded in the response text. 

#### Appointment example

	{"locator": "3c3375883f01027e5ca14f9760a8b853824ca4ebc0258c00e7fae4bae2571a80", 
	"start_time": 1568118, 
	"end_time": 1568120, 
	"dispute_delta": 20, 
	"encrypted_blob": "6c7687a97e874363e1c2b9a08386125e09ea000a9b4330feb33a5c698265f3565c267554e6fdd7b0544ced026aaab73c255bcc97c18eb9fa704d9cc5f1c83adaf921de7ba62b2b6ddb1bda7775288019ec3708642e738eddc22882abf5b3f4e34ef2d4077ed23e135f7fe22caaec845982918e7df4a3f949cadd2d3e7c541b1dbf77daf64e7ed61531aaa487b468581b5aa7b1da81e2617e351c9d5cf445e3391c3fea4497aaa7ad286552759791b9caa5e4c055d1b38adfceddb1ef2b99e3b467dd0b0b13ce863c1bf6b6f24543c30d", 
	"cipher": "AES-GCM-128", 
	"hash_function": "SHA256"}
	
# Check appointment
	
`/check_appointment` is a testing endpoint provided to check the status of the appointments sent to PISA. The endpoint is accessible without any type of authentication for now. `/check_appointment` accepts `HTTP GET` requests only, where the data to be provided must be the locator of an appointment. The query must match the following format:

`http://pisa_server:pisa_port/check_appointment?locator=appointment_locator`

### Appointment can be in three states

- `not_found`: meaning the locator is not recognised by the API. This could either mean the locator is wrong, or the appointment has already been fulfilled (the PISA server does not have any kind of data persistency for now).
- `being_watched`: the appointment has been accepted by the PISA server and it's being watched at the moment. This stage means that the dispute transaction has now been seen yet, and therefore no justice transaction has been published.
- `dispute_responded`: the dispute was found by the watcher and the corresponding justice transaction has been broadcast by the node. In this stage PISA is actively monitoring until the justice transaction reaches enough confirmations and making sure no fork occurs in the meantime.

### Check appointment response formats

`/check_appointment` will always reply with `json` containing the information about the requested appointment. The structure is as follows:

#### not_found

	[{"locator": appointment_locator, 
	"status":"not_found"}]
	
#### being_watched	
	[{"cipher": "AES-GCM-128",
	"dispute_delta": d,
	"encrypted_blob": eb,
	"end_time": e,
	"hash_function":  "SHA256",
	"locator": appointment_locator,
	"start_time": s,
	"status": "being_watched"}]
	
#### dispute_responded

	[{"locator": appointment_locator,
	"justice_rawtx": j,
	"appointment_end": e,
	"status": "dispute_responded"
	"confirmations": c}]
	
Notice that the response json always contains a list. Why? It is possible for both parties to send the “same locator” to our service: 

Alice wants to hire us to watch Bob’s commitment transaction.
Bob wants to front-run Alice by creating a job for his “commitment transaction” with a bad encrypted blob.  

In the above scenario, Bob can hire our service with a bad encrypted blob for the locator that should be used by Alice. Our service will try to decrypt both encrypted blobs, find the valid transaction and send it out. More generally, this potential DoS attack is possible of locators are publicly known (i.e. other watching services). 

### Data persistence

As mentioned earlier, our service has no data persistence. this means that fulfilled appointments cannot be queried from `/check_appointment`. On top of that, if our service is restarted, all jobs are lost. This is only temporary and we are currently working on it. Do not use this service for production-ready software yet and please consider it as an early-stage demo to better understand how our API will work. 


