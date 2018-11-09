# Pisa - The Accountable Third Party

This repository focuses on building an accountable third party service called Pisa that can be hired to watch channels on behalf of its users. The aim is to let anyone run a Pisa service and watch over several channel constructions (Kitsune, Counterfactual, Funfair, etc). We'll shortly present our architecture for this implementation of Pisa - but fundamentally it will let the Pisa service host "watchers" on several computers, and a central service is responsible for interacting with the state channel customer. 

## The Life-Cycle of Hiring Pisa 

The customer wants to hire the Pisa service to watch the channel on their behalf. Briefly, it'll involve the following: 

* Customer sends an appointment to Pisa (i.e. signatures from all parties, state hash, version)
* Pisa inspects the appointment (i.e. verify that its legitimate and can be used to resolve a future dispute)
* Pisa generates a secret "s" and hashes it to compute the receiptHash i.e. receiptHash = H(S). 
* Pisa sends the appointment (and the receiptHash) to all watchers under its control (i.e. independent servers running geth + watching service)
* All watchers will inspect the appointment (i.e. again, verify that its legitimate and can be used to resolve a future dispute) 
* Each watcher will sign a receipt and send it back to Pisa. 
* Once Pisa has received k of n signatures, all signatures are aggregated into a single signature. 
** In other words, there will be a threshold scheme to ensure that a sufficient number of watchers have accepted the job before the receipt is signed by Pisa's public key. 
* Pisa will send the signed receipt back to the customer 
* Customer sets up the conditional transfer to Pisa
* Pisa reveals the secret "s" to the customer, and the transfer is complete. 

## Limitations of above design 

* The customer can send an appointment to Pisa, but not pay Pisa. 
** Our focus is on resilience / dependability. We want to outsource the job to several watchers, and then not "cancel" it in the future. If a customer doesn't pay, then Pisa will refuse all future jobs from the customer's key + state channel. 
** This isn't an issue with the Pisa protocol, but just our current architecture design. 
