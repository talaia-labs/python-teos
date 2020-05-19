index_pattern = {
    "attributes" : {
        "timeFieldName" : "doc.time",
        "title" : "logs*"
    }
}

visualizations = {
    "available_user_slots_visual": {
        "attributes" : {
            "kibanaSavedObjectMeta" : {
               "searchSourceJSON" : "{\"query\":{\"query\":\"\",\"language\":\"lucene\"},\"filter\":[{\"$state\":{\"store\":\"appState\"},\"meta\":{\"alias\":null,\"disabled\":false,\"key\":\"query\",\"negate\":false,\"type\":\"custom\",\"value\":\"{\\\"exists\\\":{\\\"field\\\":\\\"doc.response.available_slots\\\"}}\",\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index\"},\"query\":{\"exists\":{\"field\":\"doc.response.available_slots\"}},\"size\":1,\"sort\":[{\"doc.time\":{\"order\":\"desc\",\"unmapped_type\":\"date\"}}]}],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"
            },
            "visState" : "{\"title\":\"Available user slots\",\"type\":\"goal\",\"params\":{\"addLegend\":true,\"addTooltip\":true,\"dimensions\":{\"series\":[{\"accessor\":0,\"aggType\":\"terms\",\"format\":{\"id\":\"terms\",\"params\":{\"id\":\"number\",\"missingBucketLabel\":\"Missing\",\"otherBucketLabel\":\"Other\",\"parsedUrl\":{\"basePath\":\"\",\"origin\":\"https://469de2aae64a4695a2b197c687a00716.us-central1.gcp.cloud.es.io:9243\",\"pathname\":\"/app/kibana\"}}},\"label\":\"doc.response.available_slots: Descending\",\"params\":{}}],\"x\":null,\"y\":[{\"accessor\":1,\"aggType\":\"max\",\"format\":{\"id\":\"number\",\"params\":{\"parsedUrl\":{\"basePath\":\"\",\"origin\":\"https://469de2aae64a4695a2b197c687a00716.us-central1.gcp.cloud.es.io:9243\",\"pathname\":\"/app/kibana\"}}},\"label\":\"Available user slots\",\"params\":{}}]},\"gauge\":{\"alignment\":\"automatic\",\"autoExtend\":false,\"backStyle\":\"Full\",\"colorSchema\":\"Green to Red\",\"colorsRange\":[{\"from\":0,\"to\":200}],\"gaugeColorMode\":\"None\",\"gaugeStyle\":\"Full\",\"gaugeType\":\"Arc\",\"invertColors\":false,\"labels\":{\"color\":\"black\",\"show\":true},\"orientation\":\"vertical\",\"outline\":false,\"percentageMode\":true,\"scale\":{\"color\":\"rgba(105,112,125,0.2)\",\"labels\":false,\"show\":false,\"width\":2},\"style\":{\"bgColor\":false,\"bgFill\":\"rgba(105,112,125,0.2)\",\"fontSize\":60,\"labelColor\":false,\"subText\":\"\"},\"type\":\"meter\",\"useRanges\":false,\"verticalSplit\":false},\"isDisplayWarning\":false,\"type\":\"gauge\"},\"aggs\":[{\"id\":\"1\",\"enabled\":true,\"type\":\"max\",\"schema\":\"metric\",\"params\":{\"field\":\"doc.response.available_slots\",\"customLabel\":\"Available user slots\"}},{\"id\":\"2\",\"enabled\":true,\"type\":\"terms\",\"schema\":\"group\",\"params\":{\"field\":\"doc.response.available_slots\",\"orderBy\":\"custom\",\"orderAgg\":{\"id\":\"2-orderAgg\",\"enabled\":true,\"type\":\"max\",\"schema\":\"orderAgg\",\"params\":{\"field\":\"doc.time\"}},\"order\":\"desc\",\"size\":1,\"otherBucket\":false,\"otherBucketLabel\":\"Other\",\"missingBucket\":false,\"missingBucketLabel\":\"Missing\"}}]}",
            "uiStateJSON" : "{\"vis\":{\"defaultColors\":{\"0 - 100\":\"rgb(0,104,55)\"},\"legendOpen\":true,\"colors\":{\"0 - 100\":\"#E0752D\"}}}",
            "version" : 1,
            "title" : "Available user slots",
            "description" : "This is how many user slots are used up compared to the maximum number of users this watchtower can hold."
         },
         "references" : [
             {
                "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09",
                "name" : "kibanaSavedObjectMeta.searchSourceJSON.index",
                "type" : "index-pattern"
             },
             {
                "type" : "index-pattern",
                "name" : "kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index",
                "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09"
             }
          ]
    },
    "Total_stored_appointments_visual": {
        "attributes" : {
            "visState" : "{\"title\":\"Total appointments\",\"type\":\"metric\",\"params\":{\"metric\":{\"percentageMode\":false,\"useRanges\":false,\"colorSchema\":\"Green to Red\",\"metricColorMode\":\"None\",\"colorsRange\":[{\"type\":\"range\",\"from\":0,\"to\":10000}],\"labels\":{\"show\":true},\"invertColors\":false,\"style\":{\"bgFill\":\"#000\",\"bgColor\":false,\"labelColor\":false,\"subText\":\"\",\"fontSize\":60}},\"dimensions\":{\"metrics\":[{\"type\":\"vis_dimension\",\"accessor\":0,\"format\":{\"id\":\"number\",\"params\":{\"parsedUrl\":{\"origin\":\"https://469de2aae64a4695a2b197c687a00716.us-central1.gcp.cloud.es.io:9243\",\"pathname\":\"/app/kibana\",\"basePath\":\"\"}}}}]},\"addTooltip\":true,\"addLegend\":false,\"type\":\"metric\"},\"aggs\":[{\"id\":\"1\",\"enabled\":true,\"type\":\"sum\",\"schema\":\"metric\",\"params\":{\"field\":\"doc.watcher_appts\",\"customLabel\":\"Appointments in watcher\"}},{\"id\":\"2\",\"enabled\":true,\"type\":\"sum\",\"schema\":\"metric\",\"params\":{\"field\":\"doc.responder_appts\",\"customLabel\":\"Appointments in responder\"}}]}",
            "description" : "",
            "version" : 1,
            "kibanaSavedObjectMeta" : {
               "searchSourceJSON" : "{\"query\":{\"query\":\"\",\"language\":\"lucene\"},\"filter\":[],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"
            },
            "uiStateJSON" : "{}",
            "title" : "Total appointments"
        },
        "references" : [
            {
               "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09",
               "type" : "index-pattern",
               "name" : "kibanaSavedObjectMeta.searchSourceJSON.index"
            }
        ]
    },
    "register_requests_visual": {
        "attributes" : {
           "description" : "",
           "version" : 1,
           "title" : "register requests",
           "visState" : "{\"title\":\"register requests\",\"type\":\"histogram\",\"params\":{\"type\":\"histogram\",\"grid\":{\"categoryLines\":false},\"categoryAxes\":[{\"id\":\"CategoryAxis-1\",\"type\":\"category\",\"position\":\"bottom\",\"show\":true,\"style\":{},\"scale\":{\"type\":\"linear\"},\"labels\":{\"show\":true,\"filter\":true,\"truncate\":100},\"title\":{}}],\"valueAxes\":[{\"id\":\"ValueAxis-1\",\"name\":\"LeftAxis-1\",\"type\":\"value\",\"position\":\"left\",\"show\":true,\"style\":{},\"scale\":{\"type\":\"linear\",\"mode\":\"normal\"},\"labels\":{\"show\":true,\"rotate\":0,\"filter\":false,\"truncate\":100},\"title\":{\"text\":\"Count\"}}],\"seriesParams\":[{\"show\":true,\"type\":\"histogram\",\"mode\":\"stacked\",\"data\":{\"label\":\"Count\",\"id\":\"1\"},\"valueAxis\":\"ValueAxis-1\",\"drawLinesBetweenPoints\":true,\"lineWidth\":2,\"showCircles\":true}],\"addTooltip\":true,\"addLegend\":true,\"legendPosition\":\"right\",\"times\":[],\"addTimeMarker\":false,\"labels\":{\"show\":false},\"thresholdLine\":{\"show\":false,\"value\":10,\"width\":1,\"style\":\"full\",\"color\":\"#E7664C\"},\"dimensions\":{\"x\":null,\"y\":[{\"accessor\":0,\"format\":{\"id\":\"number\"},\"params\":{},\"label\":\"Count\",\"aggType\":\"count\"}]}},\"aggs\":[{\"id\":\"1\",\"enabled\":true,\"type\":\"count\",\"schema\":\"metric\",\"params\":{}},{\"id\":\"2\",\"enabled\":true,\"type\":\"date_histogram\",\"schema\":\"segment\",\"params\":{\"field\":\"doc.time\",\"useNormalizedEsInterval\":true,\"scaleMetricValues\":false,\"interval\":\"auto\",\"drop_partials\":false,\"min_doc_count\":1,\"extended_bounds\":{}}}]}",
           "uiStateJSON" : "{\"vis\":{\"colors\":{\"Count\":\"#F9934E\"}}}",
           "kibanaSavedObjectMeta" : {
              "searchSourceJSON" : "{\"query\":{\"query\":\"\",\"language\":\"lucene\"},\"filter\":[{\"$state\":{\"store\":\"appState\"},\"meta\":{\"alias\":null,\"disabled\":false,\"key\":\"query\",\"negate\":false,\"type\":\"custom\",\"value\":\"{\\\"match\\\":{\\\"doc.message\\\":{\\\"query\\\":\\\"received register request\\\",\\\"operator\\\":\\\"and\\\"}}}\",\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index\"},\"query\":{\"match\":{\"doc.message\":{\"operator\":\"and\",\"query\":\"received register request\"}}}}],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"
           }
        },
        "references" : [
          {
             "name" : "kibanaSavedObjectMeta.searchSourceJSON.index",
             "type" : "index-pattern",
             "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09"
          },
          {
             "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09",
             "name" : "kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index",
             "type" : "index-pattern"
          }
        ]
    },
    "add_appointment_requests_visual": {
        "attributes" : {
            "uiStateJSON" : "{\"vis\":{\"colors\":{\"Count\":\"#CCA300\"}}}",
            "description" : "",
            "visState" : "{\"title\":\"add_appointment requests\",\"type\":\"histogram\",\"params\":{\"addLegend\":true,\"addTimeMarker\":false,\"addTooltip\":true,\"categoryAxes\":[{\"id\":\"CategoryAxis-1\",\"labels\":{\"filter\":true,\"show\":true,\"truncate\":100},\"position\":\"bottom\",\"scale\":{\"type\":\"linear\"},\"show\":true,\"style\":{},\"title\":{},\"type\":\"category\"}],\"dimensions\":{\"x\":null,\"y\":[{\"accessor\":0,\"aggType\":\"count\",\"format\":{\"id\":\"number\"},\"label\":\"Count\",\"params\":{}}]},\"grid\":{\"categoryLines\":false},\"labels\":{\"show\":false},\"legendPosition\":\"right\",\"seriesParams\":[{\"data\":{\"id\":\"1\",\"label\":\"Count\"},\"drawLinesBetweenPoints\":true,\"lineWidth\":2,\"mode\":\"stacked\",\"show\":true,\"showCircles\":true,\"type\":\"histogram\",\"valueAxis\":\"ValueAxis-1\"}],\"thresholdLine\":{\"color\":\"#E7664C\",\"show\":false,\"style\":\"full\",\"value\":10,\"width\":1},\"times\":[],\"type\":\"histogram\",\"valueAxes\":[{\"id\":\"ValueAxis-1\",\"labels\":{\"filter\":false,\"rotate\":0,\"show\":true,\"truncate\":100},\"name\":\"LeftAxis-1\",\"position\":\"left\",\"scale\":{\"mode\":\"normal\",\"type\":\"linear\"},\"show\":true,\"style\":{},\"title\":{\"text\":\"Count\"},\"type\":\"value\"}]},\"aggs\":[{\"id\":\"1\",\"enabled\":true,\"type\":\"count\",\"schema\":\"metric\",\"params\":{\"json\":\"\"}},{\"id\":\"2\",\"enabled\":true,\"type\":\"date_histogram\",\"schema\":\"segment\",\"params\":{\"field\":\"doc.time\",\"useNormalizedEsInterval\":true,\"scaleMetricValues\":false,\"interval\":\"auto\",\"drop_partials\":false,\"min_doc_count\":1,\"extended_bounds\":{}}}]}",
            "title" : "add_appointment requests",
            "kibanaSavedObjectMeta" : {
               "searchSourceJSON" : "{\"query\":{\"language\":\"lucene\",\"query\":\"\"},\"filter\":[{\"$state\":{\"store\":\"appState\"},\"meta\":{\"alias\":null,\"disabled\":false,\"key\":\"query\",\"negate\":false,\"type\":\"custom\",\"value\":\"{\\\"match\\\":{\\\"doc.message\\\":{\\\"query\\\":\\\"received add_appointment request\\\",\\\"operator\\\":\\\"and\\\"}}}\",\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index\"},\"query\":{\"match\":{\"doc.message\":{\"operator\":\"and\",\"query\":\"received add_appointment request\"}}}}],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"
            },
            "version" : 1
        },
        "references" : [
            {
               "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09",
               "type" : "index-pattern",
               "name" : "kibanaSavedObjectMeta.searchSourceJSON.index"
            },
            {
               "name" : "kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index",
               "id" : "5f36ea30-97e9-11ea-9cf8-038b68181f09",
               "type" : "index-pattern"
            }
         ]
    },
    "get_appointment_requests_visual": {
        "attributes" : {
            "version" : 1,
            "uiStateJSON" : "{\"vis\":{\"colors\":{\"Count\":\"#F2C96D\"}}}",
            "description" : "",
            "kibanaSavedObjectMeta" : {
               "searchSourceJSON" : "{\"query\":{\"language\":\"lucene\",\"query\":\"\"},\"filter\":[{\"$state\":{\"store\":\"appState\"},\"meta\":{\"alias\":null,\"disabled\":false,\"key\":\"query\",\"negate\":false,\"type\":\"custom\",\"value\":\"{\\\"match\\\":{\\\"doc.message\\\":{\\\"query\\\":\\\"received get_appointment request\\\",\\\"operator\\\":\\\"and\\\"}}}\",\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index\"},\"query\":{\"match\":{\"doc.message\":{\"operator\":\"and\",\"query\":\"received get_appointment request\"}}}}],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"
            },
            "visState" : "{\"title\":\"get_appointment requests\",\"type\":\"histogram\",\"params\":{\"addLegend\":true,\"addTimeMarker\":false,\"addTooltip\":true,\"categoryAxes\":[{\"id\":\"CategoryAxis-1\",\"labels\":{\"filter\":true,\"show\":true,\"truncate\":100},\"position\":\"bottom\",\"scale\":{\"type\":\"linear\"},\"show\":true,\"style\":{},\"title\":{},\"type\":\"category\"}],\"dimensions\":{\"x\":null,\"y\":[{\"accessor\":0,\"aggType\":\"count\",\"format\":{\"id\":\"number\"},\"label\":\"Count\",\"params\":{}}]},\"grid\":{\"categoryLines\":false},\"labels\":{\"show\":false},\"legendPosition\":\"right\",\"seriesParams\":[{\"data\":{\"id\":\"1\",\"label\":\"Count\"},\"drawLinesBetweenPoints\":true,\"lineWidth\":2,\"mode\":\"stacked\",\"show\":true,\"showCircles\":true,\"type\":\"histogram\",\"valueAxis\":\"ValueAxis-1\"}],\"thresholdLine\":{\"color\":\"#E7664C\",\"show\":false,\"style\":\"full\",\"value\":10,\"width\":1},\"times\":[],\"type\":\"histogram\",\"valueAxes\":[{\"id\":\"ValueAxis-1\",\"labels\":{\"filter\":false,\"rotate\":0,\"show\":true,\"truncate\":100},\"name\":\"LeftAxis-1\",\"position\":\"left\",\"scale\":{\"mode\":\"normal\",\"type\":\"linear\"},\"show\":true,\"style\":{},\"title\":{\"text\":\"Count\"},\"type\":\"value\"}]},\"aggs\":[{\"id\":\"1\",\"enabled\":true,\"type\":\"count\",\"schema\":\"metric\",\"params\":{\"json\":\"\"}},{\"id\":\"2\",\"enabled\":true,\"type\":\"date_histogram\",\"schema\":\"segment\",\"params\":{\"field\":\"doc.time\",\"useNormalizedEsInterval\":true,\"scaleMetricValues\":false,\"interval\":\"auto\",\"drop_partials\":false,\"min_doc_count\":1,\"extended_bounds\":{}}}]}",
            "title" : "get_appointment requests"
         },
        "references": [
          {
            "name": "kibanaSavedObjectMeta.searchSourceJSON.index",
            "type": "index-pattern",
            "id": "5f36ea30-97e9-11ea-9cf8-038b68181f09"
          },
          {
            "name": "kibanaSavedObjectMeta.searchSourceJSON.filter[0].meta.index",
            "type": "index-pattern",
            "id": "5f36ea30-97e9-11ea-9cf8-038b68181f09"
          }
        ]
    }
}

dashboard = {
    "attributes" : {
      "version" : 1,
      "title" : "Teos System Monitor",
      "optionsJSON" : "{\"hidePanelTitles\":false,\"useMargins\":true}",
      "panelsJSON" : "[{\"embeddableConfig\":{},\"gridData\":{\"h\":15,\"i\":\"d76b23fc-83b8-49a8-baf4-b1d180d857ca\",\"w\":24,\"x\":0,\"y\":0},\"panelIndex\":\"d76b23fc-83b8-49a8-baf4-b1d180d857ca\",\"version\":\"7.6.2\",\"panelRefName\":\"panel_0\"},{\"embeddableConfig\":{},\"gridData\":{\"h\":15,\"i\":\"ce940ff4-87f4-4fe8-b283-c392c08fe0d4\",\"w\":24,\"x\":24,\"y\":0},\"panelIndex\":\"ce940ff4-87f4-4fe8-b283-c392c08fe0d4\",\"version\":\"7.6.2\",\"panelRefName\":\"panel_1\"},{\"embeddableConfig\":{},\"gridData\":{\"h\":15,\"i\":\"2b7f4ad4-65b4-42de-af6c-4aaf79d8f4a2\",\"w\":24,\"x\":0,\"y\":30},\"panelIndex\":\"2b7f4ad4-65b4-42de-af6c-4aaf79d8f4a2\",\"version\":\"7.6.2\",\"panelRefName\":\"panel_2\"},{\"embeddableConfig\":{},\"gridData\":{\"h\":15,\"i\":\"d7b38be5-9516-4e2b-a86f-5c58f1eb750e\",\"w\":24,\"x\":24,\"y\":15},\"panelIndex\":\"d7b38be5-9516-4e2b-a86f-5c58f1eb750e\",\"version\":\"7.6.2\",\"panelRefName\":\"panel_3\"},{\"embeddableConfig\":{},\"gridData\":{\"h\":15,\"i\":\"8ae3cfd9-faa7-4e3e-920a-6a5705b864e9\",\"w\":24,\"x\":0,\"y\":15},\"panelIndex\":\"8ae3cfd9-faa7-4e3e-920a-6a5705b864e9\",\"version\":\"7.6.2\",\"panelRefName\":\"panel_4\"}]",
      "hits" : 0,
      "kibanaSavedObjectMeta" : {
         "searchSourceJSON" : "{\"query\":{\"language\":\"kuery\",\"query\":\"\"},\"filter\":[]}"
      },
      "description" : "",
      "timeRestore" : False
   }
}
