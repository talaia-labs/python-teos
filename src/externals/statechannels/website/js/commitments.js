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

module.exports = {
    randInt: randInt,
    squareHash: squareHash,
    squareCommit: squareCommit,
    shipHash: shipHash,
    shipCommit: shipCommit,
    verifyShipCommit: verifyShipCommit,
    verifySquareCommit: verifySquareCommit
}
    
