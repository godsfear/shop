import asyncio


status_model = {
    "object1": {
        "status1": {
            "next": ["status2", "cancel"],
            "trans_in": "tr_in_status1",
            "trans_out": "tr_out_status1",
        },
        "status2": {
            "next": ["status3", "cancel"],
            "trans_in": "tr_in_status2",
            "trans_out": "tr_out_status2",
        },
        "status3": {
            "next": ["status1", "final"],
            "trans_in": "tr_in_status3",
            "trans_out": "tr_out_status3",
        },
        "cancel": {
            "next": [],
            "trans_in": "tr_in_status_cancel",
            "trans_out": None,
        },
        "final": {
            "next": [],
            "trans_in": "tr_in_status_final",
            "trans_out": None,
        },
    },
}


async def main():
    ...

if __name__ == '__main__':
    asyncio.run(main())
