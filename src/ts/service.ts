import express from "express";
import httpContext from "express-http-context";
import logger from "./logger";
import { parseAppointment } from "./dataEntities/appointment";
import { Inspector } from "./inspector";
import { Watcher } from "./watcher";
import { setRequestId } from "./customExpressHttpContext";
import { Server } from "http";

// TODO: documentation on all classes

export class PisaService {
    private readonly server: Server;
    constructor(
        hostname: string,
        port: number,
        inspector: Inspector,
        watcher: Watcher
    ) {
        const app = express();
        // accept json request bodies
        app.use(express.json());
        // use http context middleware to create a request id available on all requests
        app.use(httpContext.middleware);
        app.use((req, res, next) => {
            setRequestId();
            next();
        });

        // TODO: json configuration object
        // TODO: does this provider even exist? validation
        // TODO: should be including ganache-core as a lib

        // TODO: this handler lacks tests
        app.post("/appointment", this.appointment(inspector, watcher));

        // TODO: replace with a more useful message
        const service = app.listen(port, hostname);
        logger.info(`PISA listening on: ${hostname}:${port}.`);
        this.server = service;
    }

    private appointment(inspector: Inspector, watcher: Watcher) {
        return async (req: express.Request, res: express.Response, next: express.NextFunction) => {
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
        };
    }

    public stop() {
        // TODO: could be called twice, protect?
        this.server.close(logger.info(`PISA shutdown.`));

        // TODO: we need a graceful teardown procedure
    }
}

// TODO: we need crash recovery, currently appointments are not persisted to storage
