pragma solidity ^0.4.2;

import "truffle/Assert.sol";
import "truffle/DeployedAddresses.sol";
import "./ExecutionProxy.sol";
import "../contracts/RockPaperScissors.sol";
import "./RpsProxy.sol";
import "../contracts/StateChannel.sol";

contract Test_RockPaperScissors_DistributeExtended {
    uint256 public initialBalance = 10 ether;
    
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

    function commitReveal0NotReveal1AndDistribute (
        RpsProxy player0, RpsProxy player1,
        RockPaperScissors.Choice choice0, RockPaperScissors.Choice choice1, 
        bytes32 blind0, bytes32 blind1) public {

        //commit
        player0.commit.value(commitAmount)(keccak256(abi.encodePacked(player0, choice0, blind0)));
        player1.commit.value(commitAmount)(keccak256(abi.encodePacked(player1, choice1, blind1)));
        
        //reveal
        player0.reveal(choice0, blind0);

        //distribute
        player0.distribute();
    }

    function commitReveal1NotReveal0AndDistribute (
        RpsProxy player0, RpsProxy player1,
        RockPaperScissors.Choice choice0, RockPaperScissors.Choice choice1, 
        bytes32 blind0, bytes32 blind1) public {

        //commit
        player0.commit.value(commitAmount)(keccak256(abi.encodePacked(player0, choice0, blind0)));
        player1.commit.value(commitAmount)(keccak256(abi.encodePacked(player1, choice1, blind1)));
        
        //reveal
        player1.reveal(choice1, blind1);
        
        //distribute
        player0.distribute();
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

        Assert.equal(playerAddress0, player0.playerAddress, "Player 0 address does not equal supplied one.");
        Assert.equal(uint(choice0), uint(player0.choice), "Player 0 choice does not equal supplied one.");
        Assert.equal(commitment0, player0.commitment, "Player 0 commitment does not equal supplied one.");

        Assert.equal(playerAddress1, player1.playerAddress, "Player 1 address does not equal supplied one.");
        Assert.equal(uint(choice1), uint(player1.choice), "Player 1 choice does not equal supplied one.");
        Assert.equal(commitment1, player1.commitment, "Player 1 commitment does not equal supplied one.");
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
    
    function testDistributeOnlyPlayer0ChoiceRevealedWinsAfterRevealDeadlineReached() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, 0, createStateChannel());
        RpsProxy player0 = new RpsProxy(rps);
        RpsProxy player1 = new RpsProxy(rps);
        commitReveal0NotReveal1AndDistribute(player0, player1, RockPaperScissors.Choice.Scissors, RockPaperScissors.Choice.Rock, rand1, rand2);

        // check the balance of player 0 and player 1
        Assert.equal(address(player0).balance, betAmount * 2 + depositAmount, "Player 0 did not win.");
        Assert.equal(address(player1).balance, 0, "Player 1 did not loose all money.");
        assertStateEmptied(rps);
    }

    function testDistributeOnlyPlayer1ChoiceRevealedWinsAfterRevealDeadlineReached() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, 0, createStateChannel());
        RpsProxy player0 = new RpsProxy(rps);
        RpsProxy player1 = new RpsProxy(rps);
        commitReveal1NotReveal0AndDistribute(player0, player1, RockPaperScissors.Choice.Scissors, RockPaperScissors.Choice.Rock, rand1, rand2);

        // check the balance of player 0 and player 1
        Assert.equal(address(player1).balance, betAmount * 2 + depositAmount, "Player 1 did not win.");
        Assert.equal(address(player0).balance, 0, "Player 0 did not loose all money.");
        assertStateEmptied(rps);
    }

    function testDistributeOnlyPlayer0ChoiceRevealedNoOneWinsBeforeDeadline() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy player0 = new ExecutionProxy(rps);
        RpsProxy player1 = new RpsProxy(rps);

        //commit
        bytes32 commitment0 = keccak256(abi.encodePacked(player0, RockPaperScissors.Choice.Rock, rand1));
        bytes32 commitment1 = keccak256(abi.encodePacked(player1, RockPaperScissors.Choice.Paper, rand2));
        RockPaperScissors(player0).commit.value(commitAmount)(commitment0);
        player0.execute();
        player1.commit.value(commitAmount)(commitment1);

        //reveal
        RockPaperScissors(player0).reveal(RockPaperScissors.Choice.Rock, rand1);
        player0.execute();
        
        //distribute
        RockPaperScissors(player0).distribute();
        bool result = player0.execute();

        // TODO: check the balance of player 0 and player 1
        Assert.isFalse(result, "Distribute succeeded before deadline.");        
        assertPlayersEqual(rps, RockPaperScissors.CommitChoice(player0, commitment0, RockPaperScissors.Choice.Rock), RockPaperScissors.CommitChoice(player1, commitment1, RockPaperScissors.Choice.None));
    }



    // TODO: update this test - it was the old 'allow' distribute
    // function testDistributeSendBackMoneyIfNoReveals() public {
    //     //TODO: we shouldnt have this pattern - reveal should not work and we should add the second user to the commit
    //     RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, 0);
    //     RpsProxy player0 = new RpsProxy(rps);
    //     RpsProxy player1 = new RpsProxy(rps);

    //     //commit
    //     player0.commit.value(commitAmount)(keccak256(abi.encodePacked(player0, RockPaperScissors.Choice.Rock, rand1)));
    //     player1.commit.value(commitAmount)(keccak256(abi.encodePacked(player1, RockPaperScissors.Choice.Paper, rand2)));
        
    //     //distribute
    //     player0.distribute();

    //     // check the balance of player 0 and player 1
    //     Assert.equal(address(player0).balance, 0, "Player 0 received money back from distribute before reveal.");
    //     Assert.equal(address(player1).balance, 0, "Player 1 received money back from distribute before reveal.");
    //     //assertStateEmptied(rps);
    // }
}