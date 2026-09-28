# tesserae-widget-family-dashboard
Simple full-page dashboard widget for Tesserae

Heavily influenced by the straightforward design of [family-e-ink-dashboard](https://github.com/stefanthoss/family-e-ink-dashboard), the goal is to provide a useful widget for family members (kids especially) to see the date/day-of-the-week, what the weather will be like, and what events are planned for the day.

## Features

- Optimized for ReTerminal E1001 and monochrome displays.
- Large starting hour and first-word of events for reading from across the room.
- Weather icon and high/low for outfit planning.
- Large day of week for learning the days of the week and remembering if it's late-start or not.
- Google Calendar API integration (allows accessing event label colors).
- Mapping of event colors to Phosphor icons for monochrome displays.

## Use / Installation

Requires you run `pip install google-api-python-client google-auth` on your Tesserae server in order to connect to Google's services

### AI Disclosure
Gemini was used to create the initial widget, and likely will be used for some modifications. A human will be doing fine tuning (since the LLM code is always not *quite* right).
