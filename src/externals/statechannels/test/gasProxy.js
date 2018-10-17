const cTable = require("console.table");

// TODO: clean up and refactor this file - it could be a nice util

let createMethodGasProxy = (prop, obj, gasLib) => {
    let handlerMethod = {
        apply: (target, that, args) => {
            let result = target.apply(that, args);

            if (typeof result === "object" && "then" in result) {
                return result.then(success => {
                    if (typeof success === "object" && "receipt" in success && "gasUsed" in success["receipt"]) {
                        gasLib.push({ method: prop, gasUsed: success.receipt.gasUsed });
                    }
                    return success;
                });
            } else return result;
        }
    };

    return new Proxy(obj, handlerMethod);
};

// accepts objects of the form:
// { method: string, gasUsed: number, parameters: object[] }

let createContractGasProxy = (contract, gasLib, web3) => {
    let handlerMain = {
        get: (obj, prop) => {
            if (prop in obj) {
                let g = obj[prop];

                if (typeof g === "function" && "call" in g && "sendTransaction" in g) {
                    return createMethodGasProxy(prop, g, gasLib, web3);
                } else {
                    return g;
                }
            } else return undefined;
        }
    };

    return new Proxy(contract, handlerMain);
};

let createGasProxy = (contractType, gasLib, web3) => {
    const recordGasAndCreateContractProxy = (prop, val) => {
        let contractHandler = {
            apply: (target, that, args) => {
                let result = target.apply(that, args);
                if (typeof result === "object" && "then" in result) {
                    return result.then(success => {
                        // new doesnt have a receipt, so get one and record the gas
                        return web3.eth.getTransactionReceipt(success.transactionHash).then(receipt => {
                            gasLib.push({ method: prop, gasUsed: receipt.gasUsed });
                            // the result of calling new is contract, for which we want a gas proxy
                            return createContractGasProxy(success, gasLib, web3);
                        });
                    });
                }
            }
        };

        return new Proxy(val, contractHandler);
    };

    let handlerMain = {
        get: (obj, prop) => {
            if (prop in obj) {
                let g = obj[prop];
                if (prop === "new" && typeof g === "function") {
                    // proxy the "new" function
                    return recordGasAndCreateContractProxy(prop, g);
                } else return g;
            }
        }
    };

    return new Proxy(contractType, handlerMain);
};

///////////////////////////////////////// web3 proxy - doesnt work ///////////////////////////////

const createProxyGasLogging = (sendFunc, gasLib) => {
    let sendHandler = {
        apply: (target, that, args) => {
            let result = target.apply(that, args);
            // the result should be a promise
            if (typeof result === "object" && "then" in result) {
                return result.then(receipt => {
                    // the promise should contain a transaction receipt, which should contain gas used
                    if (typeof receipt === "object" && "gasUsed" in receipt) {
                        gasLib.push({ method: "web3:" + prop, gasUsed: receipt.receipt.gasUsed });
                    }
                    return receipt;
                });
            } else return result;
        }
    };

    return new Proxy(sendFunc, sendHandler);
};

const createProxyMethodsOnInvoke = (func, depth, gasLib) => {
    const invokeHandler = {
        apply: (target, that, args) => {
            let result = target.apply(that, args);

            return createProxyMethods(result, depth + 1, gasLib);
        }
    };

    return new Proxy(func, invokeHandler);
};

const createProxyMethods = (objInput, depth, gasLib) => {
    // TODO: check each of these args
    if(typeof objInput !== "function" && typeof objInput !== "object") return objInput;

    if (depth > 10) {
        // dont proxy, just return the current
        return objInput;
    }
    const handler = {
        get: (obj, prop) => {
            const val = Reflect.get(obj, prop);
            if(!obj.hasOwnProperty(prop) && prop !== "deploy" && prop !== "send") return val;
            // if this is an object, wrap it in this handler
            console.log(prop)
            if (prop === "send" && typeof prop === "function") {
                // wrap this obj in an APPLY proxy, and return that
                // TODO: check this hasnt already been applied? how could that happen?
                console.log("hit send")
                return createProxyGasLogging(val, gasLib);
            } else {
                // if (prop === "prototype") {
                //     // TODO: investigate error:
                //     // TypeError: 'get' on proxy: property 'prototype' is a read-only and non-configurable dataproperty on the proxy target but the proxy did not return its actual value (expected '[objectArray]' but got '[object Object]')
                //     return val;
                // } 
                // else if(prop === "apply"){
                //     // dont proxy the apply function
                //     return val;
                // }
                if (typeof val === "object") {
                    // if it's a object, wrap it in this
                    return createProxyMethods(val, depth + 1, gasLib);
                } else if (typeof val === "function") {
                    // if it's a function, we need to wrap it's return values in this, as well as wrapping this in this
                    // therefore wrap in this and another proxy
                    const proxiedFunc = createProxyMethodsOnInvoke(val, depth + 1, gasLib);

                    return createProxyMethods(proxiedFunc, depth + 1, gasLib);
                } else if (typeof val === "array") {
                    // could be an array, do we care about the possible objects within it? yes
                    // proxy any objects in the array, by wrapping it an [] proxy

                    // for now just return val
                    return val;
                } else {
                    return val;
                }
            }
        }
    };
    return new Proxy(objInput, handler);
};

const createWeb3ContractProxy = (contract, gasLib) => {
    return createProxyMethods(contract, 1, gasLib);
    
};

const setWeb3Proxy = (web3, gasLib) => {
    // when 'new' is called on the web3.eth.Contract method
    // we'll call it then wrap the result in a proxy

    const newContractHandler = {
        construct: (target, args) => {
            const contract = new target(...args);
            return createWeb3ContractProxy(contract, gasLib);
        }
    };

    web3.eth.Contract = new Proxy(web3.eth.Contract, newContractHandler);
};


////////////////////////////////////////////////////////////////////////////////////////////////////////

const logGasLib = gasLib => {
    let reducer = (accumulator, currentValue) => {
        let records = accumulator.filter(a => a.method === currentValue.method);
        if (records && records[0]) {
            // update
            const record = records[0];
            record.totalGas += currentValue.gasUsed;
            record.timesCalled += 1;
            return accumulator;
        } else {
            const aggr = {
                method: currentValue.method,
                totalGas: currentValue.gasUsed,
                timesCalled: 1,
                averageGas: () => {
                    return aggr.totalGas / aggr.timesCalled;
                }
            };

            // push
            accumulator.push(aggr);
            return accumulator;
        }
    };
    let aggregates = gasLib.reduce(reducer, []);
    let total = {
        method: "TOTAL",
        totalGas: aggregates.map(s => s.totalGas).reduce((accum, curr) => accum + curr, 0),
        timesCalled: aggregates.map(s => s.timesCalled).reduce((accum, curr) => accum + curr, 0),
        averageGas: () => {
            if (total.totalGas === 0) return 0;
            return total.totalGas / total.timesCalled;
        }
    };
    aggregates.push(total);

    // execute aggregate functions
    const bufferedAggregates = aggregates.map(a => {
        let ba = {};
        for (const key in a) {
            if (a.hasOwnProperty(key)) {
                const element = a[key];
                if (typeof element === "function") {
                    ba[key] = element();
                } else {
                    ba[key] = element;
                }
            }
        }
        return ba;
    });

    console.table(bufferedAggregates);
};

module.exports = {
    createGasProxy,
    logGasLib,
    setWeb3Proxy
};
