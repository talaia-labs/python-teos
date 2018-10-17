export class TimeLogger {
    private constructor() {}

    public static theLogger = new TimeLogger();
    messageLogs: TimeLog[] = [];
    dataLogs: TimeDataLog[] = [];
    timeSpanDataLogs: TimeSpanDataLog[] = []
    timeSpanDataSubSubLogs: TimeSpanDataSubSubLog[] = []

    public messageLog(address: string) {
        return (eventName: string) => {
            const l = new TimeLog(address, eventName);
            //console.log(l.serialise());
            this.messageLogs.push(l);
        };
    }

    public dataLog(address: string, event: string, subEvent: string, data: string, id?: number) {
        let dataLog = new TimeDataLog(address, event, subEvent, data, id);
        this.dataLogs.push(dataLog);
        return dataLog;
    }

    public dataSpanLog(address: string, event: string, subEvent: string, data: string, timeSpan: number){
        this.timeSpanDataLogs.push(new TimeSpanDataLog(address, event, subEvent, data, timeSpan))
    }

    public dataSpanSubSubLog(address: string, event: string, subEvent: string, subSubEvent: string, data: string, timeSpan: number){
        this.timeSpanDataSubSubLogs.push(new TimeSpanDataSubSubLog(address, event, subEvent, subSubEvent, data, timeSpan))
    }

    public formatDataLogs() {
        let groupBy = function(xs, key) {
            return xs.reduce(function(rv, x) {
                (rv[x[key]] = rv[x[key]] || []).push(x);
                return rv;
            }, {});
        };

        let getEventName = (name: string) => {
            return name.split("-")[0];
        };

        let groups = groupBy(this.dataLogs, "id");

        let timeLogs = Object.keys(groups).map(logPairKey => {
            const logPair = groups[logPairKey];
            let startLog: TimeDataLog;
            let endLog: TimeDataLog;

            // find the start, and the end
            if ((logPair[0] as TimeDataLog).event.endsWith("start")) {
                startLog = logPair[0];
                endLog = logPair[1];
            } else {
                endLog = logPair[0];
                startLog = logPair[1];
            }
            return {
                event: getEventName(startLog.event),
                subEvent: startLog.subEvent,
                timeSpan: endLog.time - startLog.time
            };
        });

        let subEventGroups = groupBy(timeLogs, "subEvent");
        let eventTotals = Object.keys(subEventGroups).map(subGroupKey => {
            const subGroup = subEventGroups[subGroupKey];
            let actionGroups = groupBy(subGroup, "event");
            // sum all the action groups
            let totals = Object.keys(actionGroups).map(key =>
                actionGroups[key].reduce(
                    (a, b) => {
                        return {
                            event: b.event,
                            subEvent: b.subEvent,
                            timeSpan: a.timeSpan + b.timeSpan,
                            count: a.count + 1
                        };
                    },
                    { event: "", subEvent: "", timeSpan: 0, count: 0 }
                )
            );

            return totals;
        });

        console.log(eventTotals)
        return eventTotals;
    }
}

let globalCount = 0;

class TimeSpanDataLog {
    constructor(
        public readonly player: string,
        public readonly event: string,
        public readonly subEvent: string,
        public readonly data: string,
        public readonly timeSpan: number
    ) {
    }

    serialise(): string {
        return `${this.player}:${this.event}:${this.subEvent}:${this.timeSpan}:${this.data}`;
    }
}

class TimeSpanDataSubSubLog {
    constructor(
        public readonly player: string,
        public readonly event: string,
        public readonly subEvent: string,
        public readonly subSubEvent: string,
        public readonly data: string,
        public readonly timeSpan: number
    ) {
    }

    serialise(): string {
        return `${this.player}:${this.event}:${this.subEvent}:${this.subSubEvent}:${this.timeSpan}:${this.data}`;
    }
}

class TimeLog {
    public readonly time: number;
    public readonly id: number;
    constructor(public readonly player: string, public readonly event: string) {
        this.id = globalCount;
        globalCount++;
        this.time = Date.now();
    }
    serialise(): string {
        return `${this.player}:${this.time}:${this.event}`;
    }
}

class TimeDataLog {
    public readonly time: number;
    public readonly id: number;

    constructor(
        public readonly player: string,
        public readonly event: string,
        public readonly subEvent: string,
        public readonly data: string,
        id?: number
    ) {
        if (id) this.id = id;
        else this.id = globalCount;

        globalCount++;
        this.time = Date.now();
    }

    serialise(): string {
        return `${this.player}:${this.event}:${this.subEvent}:${this.time}:${this.data}`;
    }
}
