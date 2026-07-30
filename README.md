# BLife Concierge Packages - Home Assistant Integration

A custom Home Assistant integration for tracking packages at your building's concierge desk. Uses the Spike Global platform API that underpins the B.Life mobile app.

<img width="465" height="112" alt="Screenshot_20260611_134324" src="https://github.com/user-attachments/assets/2509fbc2-e534-429e-9cef-96b1b0ab95f5" />

## Features

- **Simple setup**: Username and password only — no device ID required
- **Async-first**: Built with modern async patterns using DataUpdateCoordinator
- **Package sensor**: Count of pending packages with full details as attributes
- **Locker details**: Access code and locker description fetched for each pending package
- **Auto-refresh**: Polls every 5 minutes
- **Reauth support**: Handles token expiry gracefully

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant
2. Click on **Integrations**
3. Click the three dots menu → **Custom repositories**
4. Add this repository URL and select **Integration** as the category
5. Install "BLife Concierge Packages"
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/blife_packages` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "BLife Concierge Packages"
4. Enter your credentials:
   - **Username**: Your B.Life account email
   - **Password**: Your B.Life account password

## Sensors

### Packages Ready to Collect

- **Entity ID**: `sensor.{firstname}_packages_ready_to_collect`
- **State**: Count of pending (uncollected) packages
- **Attributes**:
  - `packages`: List of pending packages

Each package in the list includes:

| Field | Description |
|---|---|
| `package_id` | Unique identifier |
| `reference` | Numeric pickup reference |
| `status` | `pending` or `collected` |
| `access_code` | PIN/code to open the locker |
| `locker_description` | Locker location (e.g. `Red 4`) |
| `tracking_number` | Courier tracking number (if set) |
| `created_date` | Arrival timestamp (ISO 8601) |
| `collected_date` | Collection timestamp (ISO 8601, null if pending) |

## Example Automations

### Notify when new package arrives

```yaml
automation:
  - alias: "New Package Notification"
    trigger:
      - platform: state
        entity_id: sensor.mihail_packages_ready_to_collect
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state | int > trigger.from_state.state | int }}"
    action:
      - service: notify.mobile_app
        data:
          title: "New Package!"
          message: >
            {{ trigger.to_state.attributes.packages | length }} package(s) waiting.
            {% set p = trigger.to_state.attributes.packages[0] %}
            Locker: {{ p.locker_description }}. Code: {{ p.access_code }}.
```

### Daily package reminder

```yaml
automation:
  - alias: "Daily Package Reminder"
    trigger:
      - platform: time
        at: "18:00:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.mihail_packages_ready_to_collect
        above: 0
    action:
      - service: notify.mobile_app
        data:
          title: "Package Reminder"
          message: >
            {{ states('sensor.mihail_packages_ready_to_collect') }} package(s) waiting.
            {% for p in state_attr('sensor.mihail_packages_ready_to_collect', 'packages') %}
            Ref {{ p.reference }} — {{ p.locker_description }}, code {{ p.access_code }}.
            {% endfor %}
```

## API

Authenticates against `https://auth.spikeglobal.io`, then queries the building's Spike community API via GraphQL (`POST /query`). Locker details fetched via REST (`GET /mobile/v1/delivery/{id}`) for pending packages only.

## Requirements

- Home Assistant 2024.1.0 or later
- Python 3.11+

## License

MIT License
