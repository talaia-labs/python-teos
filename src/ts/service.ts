import express from "express";
import httpContext from "express-http-context";
import { ethers } from "ethers";
import logger from "./logger";
import { parseAppointment } from "./dataEntities/appointment";
import { KitsuneInspector } from "./inspector";
import { KitsuneWatcher } from "./watcher";
import { IConfig } from "./dataEntities/config";
import { setRequestId } from "./customExpressHttpContext";
// TODO: more useful errors when loading config? - or just fail at the given point
const config = require("./config.json") as IConfig;

const app = express();
// accept json request bodies
app.use(express.json());
// use http context middleware to create a request id available on all requests
app.use(httpContext.middleware);
app.use((req, res, next) => {
    // TODO: this should be a symbol rather than a magic string
    setRequestId()
    next();
});

// TODO: json configuration object
// TODO: does this provider even exist? validation
// TODO: should be including ganache-core as a lib
const provider = new ethers.providers.JsonRpcProvider(config.jsonRpcUrl);
// TODO: is this too low?
provider.pollingInterval = 100;

// TODO: add logging and timing throughout

// TODO: this signer should come from config, and we shouldnt have to list accounts
const watcherWallet = new ethers.Wallet(config.watcherKey, provider);
const watcher = new KitsuneWatcher(provider, watcherWallet);
// // TODO: document the inspector, and watcher
// TODO: the inspector should take the dispute period value from config
const inspector = new KitsuneInspector(10, provider);

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
        await watcher.watch(appointment);

        // TODO: only copy the relevant parts of the appointment - eg not the request id
        res.send(appointment);
    } catch (doh) {
        // TODO: http status codes, we shouldnt be leaking error information
        // we pass errors to the next the default error handler
        next(doh);
    }
});

// TODO: replace with a more useful messag
app.listen(config.host.port, config.host.name);
logger.info(`PISA listening on: ${config.host.name}:${config.host.port}`);

// TODO: we need a graceful teardown procedure
// TODO: we need crash recovery, currently appointments are not persisted to storage
