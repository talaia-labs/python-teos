import httpContext from "express-http-context";
import uuid from "uuid";

const REQUEST_ID = "requestId";

export const setRequestId = () => {
    return httpContext.set(REQUEST_ID, uuid.v1());
}

export const getRequestId = () => {
    return httpContext.get(REQUEST_ID) as string;
}