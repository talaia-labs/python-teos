import { createLogger, format, transports } from "winston";
import httpContext from "express-http-context";

// TODO: do we need tests for this? not really
const myFormat = format.printf(info => {
    // get the current request id
    // TODO: is this performant? run a test
    // TODO: this only works because we're creating a logger for every request right?
    const requestId = httpContext.get("requestId");
    const requestString = requestId ? `[${requestId}] ` : "";
    return `${info.timestamp} ${requestString}${info.level}: ${info.message}`;
});

const combinedFormats = format.combine(format.timestamp(), myFormat);

const logger = createLogger({
    level: "info",
    format: combinedFormats,
    transports: [
        new transports.File({ filename: "error.log", level: "error" }),
        new transports.File({ filename: "info.log", level: "info" }),
        new transports.File({ filename: "debug.log", level: "debug" })
    ]
});

// TODO: we dont want to log during tests
//
// If we're not in production then log to the `console` with the format:
// `${info.level}: ${info.message} JSON.stringify({ ...rest }) `
//
if (process.env.NODE_ENV !== "production") {
    logger.add(
        new transports.Console({
            format: combinedFormats
        })
    );
}

export default logger;
