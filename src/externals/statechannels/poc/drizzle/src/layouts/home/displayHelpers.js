import React from "react";
import ContractForm from "./../../components/drizzle-react-componts/contractForm";
import ContractData from "./../../components/drizzle-react-componts/contractData";

export const SimpleDisplayData = ({ method, contract, methodArgs }) => (
    <div>
        {method}:{methodArgs ? methodArgs.reduce((a, b, i, current) => a + ":" + b) + ":" : ""}
        <ContractData contract={contract} method={method} methodArgs={methodArgs} />
    </div>
);

export const SimpleDisplayForm = ({ method, contract, sendArgs }) => (
    <div>
        {method}:<ContractForm contract={contract} method={method} sendArgs={sendArgs} />
    </div>
);
