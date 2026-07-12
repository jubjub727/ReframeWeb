function TaskChoiceCases() -> TaskChoiceBenchmarkCase[] {
    let expected = "Explain request cannot be handled";
    [
        TaskChoiceBenchmarkCase {
            id: "desktop_photoshop",
            transcript: "Open Photoshop and resize the image on my desktop.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "flight_booking",
            transcript: "Book me a flight to Tokyo for tomorrow morning.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "bank_transfer",
            transcript: "Log into my bank and transfer 500 dollars to Alex.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "checkout_form",
            transcript: "Control the browser and submit the checkout form.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "private_email",
            transcript: "Open my private email and summarize everything from today.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "phone_call",
            transcript: "Call Sarah and explain that I will be late.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "driver_install",
            transcript: "Install the missing GPU driver for me.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "file_organization",
            transcript: "Move everything in downloads into the right project folders.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "purchase_item",
            transcript: "Buy the cheapest standing desk you can find.",
            expected_task_name: expected,
        },
        TaskChoiceBenchmarkCase {
            id: "vpn_deploy",
            transcript: "Connect to my work VPN and deploy the latest build.",
            expected_task_name: expected,
        },
    ]
}
