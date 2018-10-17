# rps
Rock-Paper-Scissors commit reveal game in a state chanel

1. npm install
1. npm run compile
1. npm run start-evm
1. in a new terminal exec command "npm run start"
1. Navigate to http://localhost:8080/ to view project directory
1. Open two tabs on of rps/web and one of scClient - these will be 'on-chain'
1. Open another two tabs on of rps/web and one of scClient - these will be 'off-chain'
1. Deploy the on-chain state channel, copy the deployed address into the on-chain rps tab and deploy the rps contract
1. Do the same for the off-chain contracts
1. Play the commitments on-chain for the 0xf17f52151ebef6c7334fad080c5704d77216b732 and 0xc5fdf4076b8f3a5357c5e395ab970b5b54098fef players, this is required currently as this is the 'payable' function.
1. Lock the on-chain contract
1. Move to the off-chain state-channel tab, copy the game-state hash from the rps tab into the state box for players 1 and 2. Enter round 1. Sign for both players
1. Start a dispute, do a set-state by providing the recently created signatures, mine enough blocks to pass the deadline, then resolve.
1. Move to the off-chain rps game, take values from the on-chain rps game and copy them into the relevant fields of the unlock section. Stage values (now stage 2) are as follow 0 = nothing, 1 after first commit, 2 after second commit, 3 after first reveal, 4 after second reveal, back to 0 after distribute.
1. Click unlock, the new state should appear on the page. Play the relevant reveals.
1. Now repeat the signing and unlocking process for the on-chain contract to move the state back there (now stage 4).
1. Once complete then click 'distribute' to show the winners and reset the state.




To run tests exec command: "npm run test"


