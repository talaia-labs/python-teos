pragma solidity ^0.4.2;

import "truffle/Assert.sol";
import "truffle/DeployedAddresses.sol";
import "./ExecutionProxy.sol";
import "../contracts/RockPaperScissors.sol";
import "./RpsProxy.sol";
import "../contracts/StateChannel.sol";

contract Test_RockPaperScissors_DistributeExtendedMoreMore {
    uint256 public initialBalance = 20 ether;
    
    uint256 depositAmount = 25;
    uint256 betAmount = 100;
    uint256 commitAmount = depositAmount + betAmount;
    
    uint256 revealSpan = 10;
    bytes32 rand1 = "abc";
    bytes32 rand2 = "123";

    function createStateChannel() private returns (StateChannel) {
        address[] memory adds;
        return new StateChannel(adds, 10);
    }

    function commitRevealAndDistribute (
        RpsProxy player0, RpsProxy player1,
        RockPaperScissors.Choice choice0, RockPaperScissors.Choice choice1, 
        bytes32 blind0, bytes32 blind1) public {

        //commit
        player0.commit.value(commitAmount)(keccak256(abi.encodePacked(player0, choice0, blind0)));
        player1.commit.value(commitAmount)(keccak256(abi.encodePacked(player1, choice1, blind1)));
        
        //reveal
        player0.reveal(choice0, blind0);
        player1.reveal(choice1, blind1);
        
        //distribute
        player0.distribute();
    }

    function assertPlayersEmpty(RockPaperScissors rps) private {
        RockPaperScissors.CommitChoice memory player0 = RockPaperScissors.CommitChoice(0, 0, RockPaperScissors.Choice.None);
        RockPaperScissors.CommitChoice memory  player1 = RockPaperScissors.CommitChoice(0, 0, RockPaperScissors.Choice.None);
        assertPlayersEqual(rps, player0, player1);
    }

    function assertStateEmptied(RockPaperScissors rps) private {
        // if all received the correct balance the contract should have been reset.
        Assert.equal(rps.revealDeadline(), 0, "Reveal deadline not reset to 0");
        Assert.equal(uint(rps.stage()), uint(RockPaperScissors.Stage.FirstCommit), "Stage not reset to first commit.");
        assertPlayersEmpty(rps);
    }

    function assertPlayersEqual(RockPaperScissors rps, RockPaperScissors.CommitChoice player0, RockPaperScissors.CommitChoice player1) private {
        address playerAddress0;
        bytes32 commitment0;
        RockPaperScissors.Choice choice0;
        (playerAddress0, commitment0, choice0) = rps.players(0);

        address playerAddress1;
        bytes32 commitment1;
        RockPaperScissors.Choice choice1;
        (playerAddress1, commitment1, choice1) = rps.players(1);

        //TODO: defo check received winnings in ALL the distributes
        Assert.equal(playerAddress0, player0.playerAddress, "Player 0 address does not equal supplied one.");
        Assert.equal(uint(choice0), uint(player0.choice), "Player 0 choice does not equal supplied one.");
        Assert.equal(commitment0, player0.commitment, "Player 0 commitment does not equal supplied one.");

        Assert.equal(playerAddress1, player1.playerAddress, "Player 1 address does not equal supplied one.");
        Assert.equal(uint(choice1), uint(player1.choice), "Player 1 choice does not equal supplied one.");
        Assert.equal(commitment1, player1.commitment, "Player 1 commitment does not equal supplied one.");
    }

    function testWinningsAreDistributedWhenOnePlayer0CannotReceive() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy player0 = new ExecutionProxy(rps);
        RpsProxy player1 = new RpsProxy(rps);

        //commit
        bytes32 commitment0 = keccak256(abi.encodePacked(player0, RockPaperScissors.Choice.Rock, rand1));
        bytes32 commitment1 = keccak256(abi.encodePacked(player1, RockPaperScissors.Choice.Rock, rand2));
        RockPaperScissors(player0).commit.value(commitAmount)(commitment0);
        player0.execute();
        player1.commit.value(commitAmount)(commitment1);

        //reveal
        RockPaperScissors(player0).reveal(RockPaperScissors.Choice.Rock, rand1);
        player0.execute();
        player1.reveal(RockPaperScissors.Choice.Rock, rand2);
        
        //distribute
        player1.distribute();

        // payer 1 should have funds, player 0 should not as we cant send money to an execution proxy - the fallback has been overridden with storage
        Assert.equal(address(player1).balance, commitAmount, "Player 1 did not receive correct amount.");
        Assert.equal(address(player0).balance, 0, "Player 0 should not receive any amount.");
        Assert.equal(rps.revealDeadline(), 0, "Deadline not reset");
        Assert.equal(uint(rps.stage()), uint(RockPaperScissors.Stage.FirstCommit), "Stage not reset");
        assertPlayersEqual(rps, RockPaperScissors.CommitChoice(0, 0, RockPaperScissors.Choice.None), RockPaperScissors.CommitChoice(0, 0, RockPaperScissors.Choice.None));
    }

    function testWinningsAreDistributedWhenOnePlayer1CannotReceive() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        RpsProxy player0 = new RpsProxy(rps);
        ExecutionProxy player1 = new ExecutionProxy(rps);

        //commit
        bytes32 commitment0 = keccak256(abi.encodePacked(player0, RockPaperScissors.Choice.Rock, rand1));
        bytes32 commitment1 = keccak256(abi.encodePacked(player1, RockPaperScissors.Choice.Rock, rand2));
        player0.commit.value(commitAmount)(commitment0);
        RockPaperScissors(player1).commit.value(commitAmount)(commitment1);
        player1.execute();
        

        //reveal
        player0.reveal(RockPaperScissors.Choice.Rock, rand1);
        RockPaperScissors(player1).reveal(RockPaperScissors.Choice.Rock, rand2);
        player1.execute();
        
        //distribute
        player0.distribute();

        // payer 1 should have funds, player 0 should not as we cant send money to an execution proxy - the fallback has been overridden with storage
        Assert.equal(address(player0).balance, commitAmount, "Player 0 did not receive correct amount.");
        Assert.equal(address(player1).balance, 0, "Player 1 should not receive any amount.");
        Assert.equal(rps.revealDeadline(), 0, "Deadline not reset");
        Assert.equal(uint(rps.stage()), uint(RockPaperScissors.Stage.FirstCommit), "Stage not reset");
        assertPlayersEqual(rps, RockPaperScissors.CommitChoice(0, 0, RockPaperScissors.Choice.None), RockPaperScissors.CommitChoice(0, 0, RockPaperScissors.Choice.None));
    }
}