const Web3 = require('web3')
const web3 = new Web3(new Web3.providers.HttpProvider('http://localhost:8545'))
const abi = require('ethereumjs-abi')
const BigNumber = require('bignumber.js')

randInt = async () => {
    return web3.utils.randomHex(16);
}

squareHash = function (r, isShip) {
    return abi.soliditySHA3(
            ['uint128', 'bool'],
            [r, isShip])
}

squareCommit = async (isShip) => {
    let r = await randInt()
    return [r, squareHash(r, isShip)]
}

shipHash = function (x1, y1, x2, y2, r) {
    return abi.soliditySHA3(
            ['uint128', 'uint8', 'uint8', 'uint8', 'uint8'],
            [r, x1, y1, x2, y2])
}

shipCommit = async (x1, y1, x2, y2) => {
    let r = await randInt()
    return [r, shipHash(x1, y1, x2, y2, r)]
}

verifyShipCommit = function (commit, x1, y1, x2, y2, r) {
    let hash = shipHash(x1, y1, x2, y2, r)
    return commit.equals(hash)
}

verifySquareCommit = function (commit, r, isShip) {
    let hash = squareHash(r, isShip)
    return commit.equals(hash)
}

signStateHash = async function (i, hstate, address, account) {
    let msg = '0x' + abi.soliditySHA3(
            ['bytes32', 'uint256', 'address'],
            [hstate, i, address]).toString('hex')
    await web3.eth.personal.unlockAccount(account, "")
    var sig = await web3.eth.sign(msg, account)
    sig = sig.slice(2)
    var r = `0x${sig.slice(0, 64)}`
    var s = `0x${sig.slice(64, 128)}`
    var v = `0x${sig.slice(128, 130)}`
    return [v,r,s] 
}

module.exports = {
    randInt: randInt,
    squareHash: squareHash,
    squareCommit: squareCommit,
    shipHash: shipHash,
    shipCommit: shipCommit,
    verifyShipCommit: verifyShipCommit,
    verifySquareCommit: verifySquareCommit
}
    
