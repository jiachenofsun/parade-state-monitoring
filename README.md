# WA_Monitoring

This project assists in the monitoring of repetitive and redundant tracking of details by automating tracking from individual reporting from WhatsApp.

## Outline

This project consists of 3 major parts:
 - WhatsApp Monitoring
 - Internal State and Tracking
 - Output and Visualization

### WhatsApp Monitoring
WhatsApp monitoring can be done via a WhatsApp bot via Selenium on Python, on a self-hosted Windows Machine. No sending of message is necessary, reducing complexity of the bot. Any message sent should be parsed, before sending to the internal state for tracking and monitoring.

### Internal State and Tracking
The internal state consists of the details of the system that is to be updated. The state is initialized, and *should* then be self-consistent pending update from WhatsApp monitoring.

Alternatively, the state can be *refreshed* on a scheduled basis, such as every morning.

### Output and Visualization
The internal state can be output to various platforms. A convenient platform can be via Telegram, as the API is readily available and is easy to access. Alternatively, the output could be sent to Google Docs for public visualization. Lastly, a custom-made visualization option could be done.

## How it works

### Initialization
At initialization, and daily at 8am, the program opens the Google Sheet, and reads in the existing (manually updated) state.

### Monitoring
Thereafter, the program will listen to a specific, pooled WhatsApp group for updates, and update the internal state accordingly. Whenever the internal state is updated, the current state is output to Google Sheet with the following details:
 - the overall state, similar to the format initially read in,
 - the details of each individual and location, and
 - the details of each detail.
