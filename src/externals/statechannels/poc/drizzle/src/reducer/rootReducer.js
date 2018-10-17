import { combineReducers } from "redux";
import appReducer from "./appReducer";
import { drizzleReducers } from "./../../adjustedDrizzle/drizzle";

const reducer = combineReducers({
    app: appReducer,
    ...drizzleReducers
});

export default reducer;
