import express from "express";
import httpContext from "express-http-context";
import logger from "./logger";
import { parseAppointment } from "./dataEntities/appointment";
import { Inspector } from "./inspector";
import { Watcher } from "./watcher";
import { setRequestId } from "./customExpressHttpContext";
import { Server } from "http";

/**
 * Hosts a PISA service at the supplied host.
 */
export class PisaService {
    private readonly server: Server;
    constructor(hostname: string, port: number, inspector: Inspector, watcher: Watcher) {
        const app = express();
        // accept json request bodies
        app.use(express.json());
        // use http context middleware to create a request id available on all requests
        app.use(httpContext.middleware);
        app.use((req: express.Request, res: express.Response, next: express.NextFunction) => {
            setRequestId();
            next();
        });
        app.post("/appointment", this.appointment(inspector, watcher));

        const service = app.listen(port, hostname);
        logger.info(`PISA listening on: ${hostname}:${port}.`);
        this.server = service;
    }

    private appointment(inspector: Inspector, watcher: Watcher) {
        return async (req: express.Request, res: express.Response, next: express.NextFunction) => {
            try {
                const appointmentRequest = parseAppointment(req.body);
                // inspect this appointment
                const appointment = await inspector.inspect(appointmentRequest);

                // start watching it if it passed inspection
                await watcher.watch(appointment);

                // TODO: only copy the relevant parts of the appointment - eg not the request id
                res.send(appointment);
            } catch (doh) {
                // we pass errors to the next the default error handler
                next(doh);
            }
        };
    }

    private closed = false;
    public stop() {
        if (!this.closed) {
            this.server.close(logger.info(`PISA shutdown.`));
            this.closed = true;
        }
    }
}
