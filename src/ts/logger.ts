import { createLogger, format, transports } from "winston";
// TODO: we're importing this logger in other places - we should allow it to be injected
import httpContext from "express-http-context";


// TODO: do we need tests for this? not really
const myFormat = format.printf(info => {
    // get the current request id
    // TODO: is this performant? run a test
    const requestId = httpContext.get("requestId");
    return `${info.timestamp} [${requestId}] ${info.level}: ${info.message}`;
  });

  const combinedFormats = format.combine(
    format.timestamp(),
    myFormat
    )

const logger = createLogger({
    level: "info",
    format: combinedFormats,
    transports: [
        // - Write to all logs with level `info` and below to `combined.log`
        // - Write all logs error (and below) to `error.log`.
        new transports.File({ filename: "error.log", level: "error" }),
        new transports.File({ filename: "combined.log" })
    ]
});

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
