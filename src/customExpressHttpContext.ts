import httpContext from "express-http-context";
import uuid from "uuid/v4";

const REQUEST_ID = "requestId";

export const setRequestId = () => {
    return httpContext.set(REQUEST_ID, uuid());
}

export const getRequestId = () => {
    return httpContext.get(REQUEST_ID) as string;
}