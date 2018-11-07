import express from "express";
import { Inspector } from "./inspector";
import { ethers } from "ethers";
import { parseAppointment, ILogAppointmentRequest } from "./dataEntities/appointment";
import { Watcher } from "./watcher";
import httpContext from "express-http-context";
import uuid from "uuid";

const app = express();
// accept json request bodies
app.use(express.json());
// use http context middleware to create a request id available on all requests
app.use(httpContext.middleware)
app.use((req, res, next) => {
    httpContext.set("requestId", uuid.v1());
    next();
})


// TODO: json configuration object
// TODO: does this provider even exist? validation
// TODO: should be including ganache-core as a lib
const provider = new ethers.providers.JsonRpcProvider("http://localhost:8545");
// TODO: is this too low
provider.pollingInterval = 100;


// TODO: add logging and timing throughout

provider.listAccounts().then(accounts => {
    // TODO: this signer should come from config, and we shouldnt have to list accounts
    const watcher = new Watcher(provider, provider.getSigner(accounts[2]));
    // // TODO: document the inspector, and watcher
    const inspector = new Inspector(10, provider);

    // TODO: this handler lacks tests
    app.post("/", async (req, res, next) => {
        try {
            // TODO: this method lacks tests:
            const appointmentRequest = parseAppointment(req.body);

            // TODO: unhandled promise rejections are coming out of ethersjs
            await inspector.inspect(appointmentRequest);

            // we've passed inspection so lets create a receipt
            const appointment = inspector.createAppointment(appointmentRequest);

            // add this appointment
            await watcher.addAppointment(appointment);

            // TODO: only copy the relevant parts of the appointment - eg not the request id
            res.send(appointment);
        } catch (doh) {
            // TODO: http status codes, we shouldnt be leaking error information
            // we pass errors to the next the default error handler
            next(doh);
        }
    });

    // TODO: replace with a more useful messgae
    let portNumber = 3000;
    console.log(`PISA starting on: http://localhost:${portNumber}`);
    app.listen(portNumber);
});

// TODO: we need a graceful teardown procedure
// TODO: we need crash recovery, currently appointments are not persisted to storage
