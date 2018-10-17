const BattleShips = artifacts.require('./BattleShips.sol')
const Web3 = require('web3')
const web3 = new Web3(new Web3.providers.HttpProvider('http://localhost:8545'))
const abi = require('ethereumjs-abi')
const BigNumber = require('bignumber.js')
const StateChannel = artifacts.require('./StateChannel.sol')

const Commit = require('./helpers/commitments.js')

contract('BattleShips', function (accounts) {
    let battleship, battleship2, boardcommitments, tx, turn, statechannel

    const player1 = accounts[1]
    const player2 = accounts[2]

//    const p1ships =[[0,0, 3,0],
//                    [0,2, 2,2],
//                    [0,4, 2,4],
//                    [0,6, 1,6],
//                    [0,8, 1,8],
//                    [8,0, 9,0],
//                    [9,2, 9,2],
//                    [9,4, 9,4],
//                    [9,6, 9,6],
//                    [9,8, 9,8]].reverse()

    const p1ships =[[0,0, 1,0],
                    [0,2, 1,2],
                    [0,4, 1,4],
                    [0,6, 1,6],
                    [0,8, 1,8],
                    [8,0, 9,0],
                    [9,2, 9,2],
                    [9,4, 9,4],
                    [9,6, 9,6],
                    [9,8, 9,8]].reverse()

    //const p1x1 = [0,0,0,0,0,8,9,9,9,9].reverse()
    //const p1y1 = [0,2,4,6,8,0,2,4,6,8].reverse()
    //const p1x2 = [3,2,2,1,1,9,9,9,9,9].reverse()
    //const p1y2 = [0,2,4,6,8,0,2,4,6,8].reverse()
    
    const p1x1 = [0,0,0,0,0,8,9,9,9,9].reverse()
    const p1y1 = [0,2,4,6,8,0,2,4,6,8].reverse()
    const p1x2 = [1,1,1,1,1,9,9,9,9,9].reverse()
    const p1y2 = [0,2,4,6,8,0,2,4,6,8].reverse()
    
    //const p1board = 
    //   [[1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    //    [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    //    [1, 0, 1, 0, 1, 0, 0, 0, 0, 0],
    //    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    //    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    //    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    //    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    //    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    //    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    //    [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]]   
    
    const p1board = 
       [[1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]]   
    
    const p1boardLiar = 
       [[1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        [1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
        [1, 0, 1, 0, 1, 0, 0, 0, 0, 0],
        [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]]   

    let p1boardCommits = []
    let p1boardBits = []
    let p1shipCommits = []  
    let p1shipBits = []

    let shipSquareBits = [] 

    before( async () => {
        statechannel = await StateChannel.new([player1, player2], 20)
        battleship = await BattleShips.new(player1, player2, '0x0')
        battleship2 = await BattleShips.new(player1, player2, statechannel.address)

        // create board commitments
        for (var i = 0; i < p1board.length; i++) {
            var row = p1board[i]
            var commitRow = []
            var bitsRow = []
            for (var j = 0; j < row.length; j++) {
                var result = await Commit.squareCommit( row[j] == 1 )
                bitsRow.push( result[0].toString('hex') )
                commitRow.push( '0x' + result[1].toString('hex') )
            }
            p1boardCommits.push(commitRow)
            p1boardBits.push(bitsRow)
            console.log('test', p1boardCommits[0][1], p1boardBits[0][1])
        }

        // create ship commits
        for (var i = 0; i < p1ships.length; i++) {
            var ship = p1ships[i]
            var result = await Commit.shipCommit(ship[0], ship[1], ship[2], ship[3])
            p1shipCommits.push( '0x' + result[1].toString('hex') )
            p1shipBits.push( result[0].toString('hex') )    
        }

        var cs = p1boardBits

        shipSquareBits = 
           [cs[9][8], cs[9][8],
            cs[9][6], cs[9][6],
            cs[9][4], cs[9][4],
            cs[9][2], cs[9][2],
            cs[8][0], cs[9][0],
            cs[0][8], cs[1][8],
            cs[0][6], cs[1][6],
            cs[0][4], cs[2][4],
            cs[0][2], cs[2][2],
            cs[0][0], cs[3][0]]

        shipSquareBits = 
           [cs[9][8], cs[9][6],
            cs[9][4], cs[9][2],
            cs[8][0], cs[9][0],
            cs[0][8], cs[1][8],
            cs[0][6], cs[1][6],
            cs[0][4], cs[1][4],
            cs[2][4], cs[0][2],
            cs[1][2], cs[2][2],
            cs[0][0], cs[1][0],
            cs[2][0], cs[3][0]]

        shipSquareBits = 
           [cs[9][8], cs[9][6],
            cs[9][4], cs[9][2],
            cs[8][0], cs[9][0],
            cs[0][8], cs[1][8],
            cs[0][6], cs[1][6],
            cs[0][4], cs[1][4],
            cs[0][2],
            cs[1][2],
            cs[0][0], cs[1][0],
            ]

        //p1shipCommits = p1shipCommits.reverse()
        //p1shipBits = p1shipBits.reverse()
                       
    })

    it('board should commit', async () => {
        // player 1 commits to a board
        tx = await battleship.commitBoard(p1boardCommits, p1shipCommits,{from: player1})
        log = tx.logs.find(log => log.event == 'BoardCommit')
        assert.equal(log.args.player, player1)
        
        var committed = await battleship.isCommitted.call(0)
        assert.equal( committed, true )

        // player 2 submits the sameboard
        tx = await battleship.commitBoard(p1boardCommits, p1shipCommits,{from: player2})
        log = tx.logs.find(log => log.event == 'BoardCommit')
        assert.equal(log.args.player, player2)
        
        var committed = await battleship.isCommitted.call(1)
        assert.equal( committed, true )
    })

    it('player 1 attacks a spot', async () => {
        // player 1 attacks (0,2)
        turn = await battleship.turn.call()
        assert( turn.eq(0) )

        tx = await battleship.attack(0, 2, {from: player1})
    
        log = tx.logs.find(log => log.event == 'Attack')
        assert.equal(log.args.player, player1)
        assert(log.args.x.eq(0))
        assert(log.args.y.eq(2))

        turn = await battleship.turn.call()
        assert( turn.eq(1) )
    })

    it('player 2 reveals attacked square', async () => {
        tx = await battleship.reveal(p1boardBits[0][2], p1board[0][2] == 1, {from: player2})
        
        log = tx.logs.find(log => log.event == 'Reveal')
        assert.equal(log.args.player, player2)
        assert.equal(log.args.hit, true)
    })

    it('player 1 hits the board again', async () => {
        // player 1 attacks (1,2)
        tx = await battleship.attack(1, 2, {from: player1})
    
        log = tx.logs.find(log => log.event == 'Attack')
        assert.equal(log.args.player, player1)
        assert(log.args.x.eq(1))
        assert(log.args.y.eq(2))
        
//        tx = await battleship.reveal(p1boardBits[1][2], p1board[1][2] == 1, {from: player2})
//        
//        log = tx.logs.find(log => log.event == 'Reveal')
//        assert.equal(log.args.player, player2)
//        assert.equal(log.args.hit, true)
    })

    it('player1 sinks the boat', async () => {
        // player 1 attacks (2,2)
//        tx = await battleship.attack(2, 2, {from: player1})
//    
//        log = tx.logs.find(log => log.event == 'Attack')
//        assert.equal(log.args.player, player1)
//        assert(log.args.x.eq(2))
//        assert(log.args.y.eq(2))
       
        // changed the order here!!!!!!!!!!!! 
        tx = await battleship.revealSink(p1boardBits[1][2], p1shipBits[8], 8, p1ships[8][0], p1ships[8][1], p1ships[8][2], p1ships[8][3], {from: player2})
        
        log = tx.logs.find(log => log.event == 'RevealSink')
        assert.equal(log.args.player, player2)
        assert(log.args.shipidx.eq(8))
    })

    it('player1 turn over with a miss', async () => {
        // player 1 attacks (6,6)
        tx = await battleship.attack(6, 6, {from: player1})
    
        log = tx.logs.find(log => log.event == 'Attack')
        assert.equal(log.args.player, player1)
        assert(log.args.x.eq(6))
        assert(log.args.y.eq(6))
        
        tx = await battleship.reveal(p1boardBits[6][6], p1board[6][6] == 1, {from: player2})
        
        log = tx.logs.find(log => log.event == 'Reveal')
        assert.equal(log.args.player, player2)
        assert.equal(log.args.hit, false)

    })

    it('player 2 attacks', async () => {
        // player 2 attacks (3,0)
        tx = await battleship.attack(1, 0, {from: player2})

        log = tx.logs.find(log => log.event == 'Attack')
        assert.equal(log.args.player, player2)
        assert(log.args.x.eq(1))
        assert(log.args.y.eq(0))
        
        tx = await battleship.reveal(p1boardBits[1][0], p1board[1][0] == 1, {from: player1})

        log = tx.logs.find(log => log.event == 'Reveal')
        assert.equal(log.args.player, player1)
        assert.equal(log.args.hit, true)
    })

    it('get the state from one game & set it in the state channel', async () => {
        await statechannel.triggerDispute({from: player1})
        let hstate = await battleship.getStateHash()
        let i = 5
        var sigs = []
        sigs = sigs.concat(await signStateHash(i, hstate, statechannel.address, player1)) 
        sigs = sigs.concat(await signStateHash(i, hstate, statechannel.address, player2)) 
        tx = await statechannel.setstate(sigs, i, hstate, {from: player1})
        log = tx.logs.find(log => log.event == 'EventEvidence')
        //assert(log.args.bestround.eq(i))
        assert.equal(log.args.hstate, hstate)
    })

    it('finish the game and claim winner', async () => {
        // player 2 sink 4x1
        let movesp2 = [[0,0]] 
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[9], 9, p1ships[9][0], p1ships[9][1], p1ships[9][2], p1ships[9][3], {from: player1})

                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(9))
                console.log('4x1 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }


        // player 2 sink 3x1
        movesp2 = [[0,2], [1,2]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[8], 8, p1ships[8][0], p1ships[8][1], p1ships[8][2], p1ships[8][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(8))
                console.log('3x1 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 3x2
        movesp2 = [[0,4], [1,4]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[7], 7, p1ships[7][0], p1ships[7][1], p1ships[7][2], p1ships[7][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(7))
                console.log('3x2 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 2x1
        movesp2 = [[0,6], [1,6]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[6], 6, p1ships[6][0], p1ships[6][1], p1ships[6][2], p1ships[6][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(6))
                console.log('2x1 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 2x2
        movesp2 = [[0,8], [1,8]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[5], 5, p1ships[5][0], p1ships[5][1], p1ships[5][2], p1ships[5][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(5))
                console.log('2x2 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 2x3
        movesp2 = [[8,0], [9,0]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[4], 4, p1ships[4][0], p1ships[4][1], p1ships[4][2], p1ships[4][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(4))
                console.log('2x3 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinkx 1x1
        movesp2 = [[9,2]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[3], 3, p1ships[3][0], p1ships[3][1], p1ships[3][2], p1ships[3][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(3))
                console.log('1x1 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 1x2
        movesp2 = [[9,4]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[2], 2, p1ships[2][0], p1ships[2][1], p1ships[2][2], p1ships[2][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(2))
                console.log('1x2 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 1x3
        movesp2 = [[9,6]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[1], 1, p1ships[1][0], p1ships[1][1], p1ships[1][2], p1ships[1][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(1))
                console.log('1x3 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }

        // player 2 sinks 1x4
        movesp2 = [[9,8]]
        for (var i = 0; i < movesp2.length; i++) {
            var move = movesp2[i]
            tx = await battleship.attack(move[0], move[1], {from: player2})
            log = tx.logs.find(log => log.event == 'Attack')
            assert.equal(log.args.player, player2)
            assert(log.args.x.eq(move[0]))
            assert(log.args.y.eq(move[1]))

            if (i == movesp2.length-1) {
                tx = await battleship.revealSink(p1boardBits[move[0]][move[1]], p1shipBits[0], 0, p1ships[0][0], p1ships[0][1], p1ships[0][2], p1ships[0][3], {from: player1})
                log = tx.logs.find(log => log.event == 'RevealSink')
                assert.equal(log.args.player, player1)
                assert(log.args.shipidx.eq(0))
                console.log('1x4 sank!')
            } else {
                tx = await battleship.reveal(p1boardBits[move[0]][move[1]], p1board[move[0]][move[1]] == 1, {from: player1})
                log = tx.logs.find(log => log.event == 'Reveal')
                assert.equal(log.args.player, player1)
                assert.equal(log.args.hit, true)
            }
        }
    })

    it('player 2 says fuck it and reveals his board', async () => {
//        tx = await battleship.checkBoard(1, shipSquareBits, p1shipBits, p1x1, p1y1, p1x2, p1y2, {from: player2})
        tx = await battleship.claimWin(shipSquareBits, p1shipBits, p1x1, p1y1, p1x2, p1y2, {from: player2})
        log = tx.logs.find(log => log.event == 'Winner')
        assert.equal(log, undefined)
    })

//    it('player 1 reveals his board since the game is over', async () => {
//        tx = await battleship.checkBoard(0, shipSquareBits, p1shipBits, p1x1, p1y1, p1x2, p1y2, {from: player1})
//        log = tx.logs.find(log => log.event == 'Winner')
//        assert.equal(log, undefined)
//    })
//
//    it('player 2 claims victory', async () => {
//        tx = await battleship.claimWin({from: player2})
//        
//        log = tx.logs.find(log => log.event == 'Winner')
//        assert.equal(log.args.player, player2)
//    })

})
