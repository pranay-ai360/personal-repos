import pandas as pd

# Your JSON sample data
data = {
    "id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
    "type": "wallet_exposure",
    "subject": {
        "asset": "ETH",
        "type": "address",
        "hash": "1MdYC22Gmjp2ejVPCxyYjFyWbQCYTGhGq8"
    },
    "customer": {
        "id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
        "reference": "foobar"
    },
    "blockchain_info": {
        "cluster": {
            "inflow_value": {
                "usd": 38383838
            },
            "outflow_value": {
                "usd": 0
            }
        }
    },
    "created_at": "2015-05-13T10:36:21.000Z",
    "updated_at": "2015-05-13T10:36:21.000Z",
    "analysed_at": "2015-05-13T10:36:21.000Z",
    "analysed_by": {
        "id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
        "type": "api_key"
    },
    "asset_tier": "full",
    "cluster_entities": [
        {
            "name": "Mt.Gox",
            "category": "Exchange",
            "is_primary_entity": True,
            "is_vasp": True
        }
    ],
    "team_id": "e333694b-c7c7-4a36-bf35-ed2615865242",
    "risk_score": 9.038007,
    "risk_score_detail": {
        "source": 6,
        "destination": 6
    },
    "error": {
        "message": "something went wrong"
    },
    "evaluation_detail": {
        "source": [
            {
                "rule_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "rule_name": "Illict",
                "risk_score": 9.038007,
                "matched_elements": [
                    {
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "contribution_percentage": 0,
                        "contribution_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "counterparty_percentage": 0,
                        "counterparty_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "indirect_percentage": 0,
                        "indirect_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "contributions": [
                            {
                                "contribution_percentage": 0,
                                "counterparty_percentage": 0,
                                "indirect_percentage": 0,
                                "entity": "AlphaBay",
                                "risk_triggers": {
                                    "name": "Binance",
                                    "category": "Dark Markets",
                                    "is_sanctioned": True,
                                    "country": [
                                        "MM"
                                    ]
                                },
                                "contribution_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "counterparty_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "indirect_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "is_screened_address": False,
                                "min_number_of_hops": 1
                            }
                        ]
                    }
                ],
                "matched_behaviors": [
                    {
                        "behavior_type": "Peeling Chain",
                        "length": 7,
                        "usd_value": 10500
                    }
                ],
                "rule_history_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "mc_analysis_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7"
            }
        ],
        "destination": [
            {
                "rule_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "rule_name": "Illict",
                "risk_score": 9.038007,
                "matched_elements": [
                    {
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "contribution_percentage": 0,
                        "contribution_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "counterparty_percentage": 0,
                        "counterparty_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "indirect_percentage": 0,
                        "indirect_value": {
                            "native": 38383838,
                            "native_major": 383.83838,
                            "usd": 383.83838
                        },
                        "contributions": [
                            {
                                "contribution_percentage": 0,
                                "counterparty_percentage": 0,
                                "indirect_percentage": 0,
                                "entity": "AlphaBay",
                                "risk_triggers": {
                                    "name": "Binance",
                                    "category": "Dark Markets",
                                    "is_sanctioned": True,
                                    "country": [
                                        "MM"
                                    ]
                                },
                                "contribution_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "counterparty_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "indirect_value": {
                                    "native": 38383838,
                                    "native_major": 383.83838,
                                    "usd": 383.83838
                                },
                                "is_screened_address": False,
                                "min_number_of_hops": 1
                            }
                        ]
                    }
                ],
                "matched_behaviors": [
                    {
                        "behavior_type": "Peeling Chain",
                        "length": 7,
                        "usd_value": 10500
                    }
                ],
                "rule_history_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7",
                "mc_analysis_id": "b7535048-76f8-4f60-bdd3-9d659298f9e7"
            }
        ]
    },
    "contributions": {
        "source": [
            {
                "entities": [
                    {
                        "name": "Alphabay",
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "entity_id": "1a93efdd-6063-4118-9748-d0a18a35fb70",
                        "is_primary_entity": True,
                        "is_vasp": True
                    }
                ],
                "contribution_percentage": 95,
                "contribution_value": {
                    "native": 0.07414304,
                    "native_major": 0.07414304,
                    "usd": 0.07414304
                },
                "counterparty_percentage": 50,
                "counterparty_value": {
                    "native": 0.04414304,
                    "native_major": 0.04414304,
                    "usd": 0.04414304
                },
                "indirect_percentage": 45,
                "indirect_value": {
                    "native": 0.03,
                    "native_major": 0.03,
                    "usd": 0.03
                },
                "is_screened_address": False,
                "min_number_of_hops": 1
            }
        ],
        "destination": [
            {
                "entities": [
                    {
                        "name": "Alphabay",
                        "category": "Dark Market",
                        "category_id": "0a52f7a2-5da8-4256-b230-df0da6f8449b",
                        "entity_id": "1a93efdd-6063-4118-9748-d0a18a35fb70",
                        "is_primary_entity": True,
                        "is_vasp": True
                    }
                ],
                "contribution_percentage": 95,
                "contribution_value": {
                    "native": 0.07414304,
                    "native_major": 0.07414304,
                    "usd": 0.07414304
                },
                "counterparty_percentage": 50,
                "counterparty_value": {
                    "native": 0.04414304,
                    "native_major": 0.04414304,
                    "usd": 0.04414304
                },
                "indirect_percentage": 45,
                "indirect_value": {
                    "native": 0.03,
                    "native_major": 0.03,
                    "usd": 0.03
                },
                "is_screened_address": False,
                "min_number_of_hops": 1
            }
        ]
    },
    "detected_behaviors": [
        {
            "behavior_type": "Peeling Chain",
            "length": 7,
            "usd_value": 10500
        }
    ],
    "changes": {
        "risk_score_change": 0.1
    },
    "workflow_status": "active",
    "workflow_status_id": 1,
    "process_status": "running",
    "process_status_id": 2,
    "triggered_rules": [],
    "screening_source": "sync"
}

# Flatten the JSON so that each nested key is represented with "__" as the separator
df = pd.json_normalize(data, sep="__")

# Save the DataFrame to an XLSX file
excel_filename = "sample.xlsx"
df.to_excel(excel_filename, index=False)