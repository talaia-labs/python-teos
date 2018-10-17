# An Empirical Evaluation of State Channels 

An experiment to empirically evaluate state channels as a scaling solution for cryptocurrencies. A summary of our work is below. 

What is the problem?
=========================

Cryptocurrencies do not scale. 

At the heart of the scaling problem is a tradeoff between "decentralisation of users" and "decentralisation of validators".

If the community can increase the throughput of transactions stored in the blockchain, then it is likely the network will have lower transaction fees. 
This can increase the set of users who can use the blockchain as transaction fees are reasonable and "affordable". 

However, simply increasing a network's throughput will directly reduce the set of users who can validate the entire network. Most home-computers cannot verify or even download 5k transactions per second. Thus we lose the property that makes a public blockchain special, i.e. holding the maintainers (i.e. miners, stakers, proof of authority, etc) of the network accountable. 

The different scaling options? 
=========================

There are several ways the community are approaching "scaling":

- New blockchain protocol
--> A DAG, Hashgraph, Avalance, etc can be used to increase the throughput of the network. But as we identified above, this reduces the set of validators on the network. 

- Sharding
--> Create "processing areas" dedicated to specific transactions. One shard for hotel bookings, one for train bookings. This distributes validation as validators only verify the shard they care about. But if the validators care about multiple shards, the problem doesn't go away. 

- Offchain 
--> All parties execute an application (or series of payments) locally amongst themselves. The blockchain is only consulted to "peg" onto the off-chain solution, to resolve disputes that may arise and to guarantee the "safety" of funds/"liveness" of the application. This reduces the blockchain's load as only a subset of transactions need to be sent. 

There are two approaches for off-chain which include sidechains (i.e. plasma) or state channels. The fundamental difference between both approaches is that in a sidechain, the users and the maintainers are distinct sets of people, whereas in a state channel the users ARE the maintainers. 

In this repo, we pursue the state channels approach. 

What is a "state" channel?
=========================

We learnt at the berlin workshop that everyone has a different definition for a state channel: 
https://binarydistrict.com/workshop/master-workshop-off-the-chain/

In this repo, we propose the following definition: 

A group of parties must peg coins to the blockchain and agree to participate in running an application off-chain. Every party collectively authorises the new state of an application locally amongst themselves. If one party does not co-operate, then the current state of the application can be stored on the blockchain, and its execution can be finished via the blockchain.

In the above, the blockchain is only used to "resolve disputes". It guarantees safety of funds for all parties, and it also guarantees liveness as the application's execution can be finished on-chain. 

How well do state channels work? 
=========================

In this repo, we focus on an empirical evaluation of state channels. 

We have built a smart contract where two players can play the game "battleship" via the blockchain. Typically, a game of battleship may require 200 transactions (in the worst case; each player hits every cell of the counterparty's board). 

We demonstrate the minimal modifications required to deploy the battleship game to work in a state channel. Effectively, all players agree to "lock the application contract" via battleship.lock() so it no longer works on-chain and it instantiates a "state channel contract". Both players can then execute the battleship game off-chain between each other. 

For every move in the game, one player proposes a command (i.e. shoot cell A,0), and both players authorise the new state (i.e. the player has shot the cell). Every new state is associated with an "incremented" counter, and the state with the largest counter will be considered "the latest state" by the state channel contract.

If one party doesn't co-operate (i.e. Bob is about to beat Alice at battleship, and she refuses to authorise the new state where she loses the game), then the other party (i.e. Bob) must trigger the dispute process. This turns off the channel and lets both players finish the game via the blockchain. It works as follows: 

- One player triggers a dispute by calling SC.triggerdispute()
- Contract enforces a "dispute time period" where both players can submit the latest "state hash" + counter .
- One or both players submit a state hash + counter using SC.setstatehash(). 
- After the "dispute time period", any player calls SC.resolve(), and the state channel contract considers the state hash with the largest counter as the final state.

To unlock the application, any player can submit the full game state to battleship.unlock(). This checks the hash of the full game state matches what is stored in the state channel and then proceeds to store the state/unlock the contract. Now the game can continue to be played via the blockchain. 

What are we learning?
=========================

In the ideal case, multiple battleship games can be executed off-chain between both players. State channels offer instant finality (i.e. the moment both parties exchange signatures - it is final), and avoid transaction fees for the entire game. 

In the worst case, both players may agree to play the battleship game, but then one party turns off the channel. Now both players are committed to playing 200+ moves/transactions via the blockchain - which incurs considerable (and not agreed upon) financial cost. 

Essentially, a state channel should only be considered an "optimistic scaling approach" as trusting every player to "co-operate" can have big implications. 

There are other lessons such as the Funfair dilemma (i.e. the dispute process cost adds an additional and potentially deadly crypto-economic element to the game), but we'll include these in the paper which should be released this month. 

As a final note, it would be really fun to have the community build bots, and let the bots compete with each other.

Other Resources (Coming soon) 
=========================

Slides: https://docs.google.com/presentation/d/1kVy77xRjzwLdUKbtHUMIhLF3eueaUf5lREwcRiDgPAk/edit?usp=sharing
Video: https://www.youtube.com/watch?v=_yOCir3radM&feature=youtu.be
