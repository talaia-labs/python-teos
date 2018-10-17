### Setup

1. Exec "truffle compile"
1. cd poc/scClient
2. For development exec "npm run watch", for a one time build run "npm run build"
3. In a new terminal run "truffle develop"
4. In a new terminal run "npm run server"
5. Navigate to localhost:8080


### Operation

The interface shows the tools for interacting with a state channel, and a small game that two players can play. The players are reading the alphabet together, when they agree on a letter they can move on to the next one. Agreement is reached when both players have signed a copy of the round and state, do this by enter these into the relevant boxes for a player and clicking "Hash and Sign". If stop cooperating they can use the state channel methods to ensure that a given state (the latest agreed) is stored in the blockchain. If you suspect an error at any point, open the developer console in confirm.

1. Deploy a state channel by clicking the "Deploy" at the top center of the page. Nothing will work on the page until this has happened.
2. Click "Next letter".
3. For player one enter the round and letter, and click "Hash and Sign".
4. Do the same for player 2
5. Click "Next letter"
6. Enter the new information for player 1, hash and sign.
7. Perhaps at this point player 2 stop cooperating, and no longer makes any updates. Player 1 only has access to Player 2's sig for round 1, so this is the latest agreed state.
8. Enter player 1 address, and trigger dispute. Verify that this sets a deadline for 10 blocks time.
9. Enter the details for round 1 into the Set State section, click Set State. Verify that this sets the round 1 state, feedback is supplied below.
10. Now click "Mine block" until the deadline has passed
11. Enter player 1 address and add click "Resolve"
12. Result should show that round 1 was set.