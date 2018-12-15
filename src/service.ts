import express, { Response } from "express";
import httpContext from "express-http-context";
import logger from "./logger";
import { parseAppointment, PublicValidationError } from "./dataEntities/appointment";
import { Inspector, PublicInspectionError } from "./inspector";
import { Watcher } from "./watcher";
import { setRequestId } from "./customExpressHttpContext";
import { Server } from "http";
import { inspect } from "util";

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

                // return the appointment
                res.status(200);
                res.send(appointment);
            } catch (doh) {
                if (doh instanceof PublicInspectionError) this.logAndSend(400, doh.message, doh, res);
                else if (doh instanceof PublicValidationError) this.logAndSend(400, doh.message, doh, res);
                else if (doh instanceof Error) this.logAndSend(500, "Internal server error.", doh, res);
                else {
                    logger.error("Error: 500. " + inspect(doh));
                    res.status(500);
                    res.send("Internal server error.");
                }
            }
        };
    }

    private logAndSend(code: number, responseMessage: string, error: Error, res: Response) {
        logger.error(`HTTP Status: ${code}.`);
        logger.error(error.stack);
        res.status(code);
        res.send(responseMessage);
    }

    private closed = false;
    public stop() {
        if (!this.closed) {
            this.server.close(logger.info(`PISA shutdown.`));
            this.closed = true;
        }
    }
}
