# sensor.avfallsor
Simple sensor for avfallsor (garbage pickup)


[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE.md)
[![hacs][hacsbadge]][hacs]
[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]


## Installation
Install using hacs or manual install

### Manual install
1. Using the tool of choice open the directory (folder) for your HA configuration (where you find `configuration.yaml`).
2. If you do not have a `custom_components` directory (folder) there, you need to create it.
3. In the `custom_components` directory (folder) create a new folder called `avfallsor`.
4. Download _all_ the files from the `custom_components/avfallsor/` directory (folder) in this repository.
5. Place the files you downloaded in the new directory (folder) you created.
6. Restart Home Assistant


## Configuration options
Key | Type | Required | Default | Description
-- | -- | -- | -- | --
`address` | `string` | `False` | `""` | Address for garbage pickup
`municipality` | `string` | `False` | `""` | Name of your 
`street_id` | `string` | `False` | `""` | Go to https://avfallsor.no/tommekalender/ enter the address and the hour number, press "vis tømmekalender" after that you get redirect to url that looks something like this: ```https://avfallsor.no/tommekalender/?id=12345&kommune=Kristiansand``` grab the id and the kommune in the url.

The sensor tries to find the your address (to find the pickup dates for your address) in this order:
1. `street_id` and `municipality`
2. `address`
3. Lat and lon that you entered when you setup home assistant.

### Yaml
So minimal yaml example could be.
````
sensor:
- platform: avfallsor
````

Full example.
```
sensor:
- platform: avfallsor
  address: "Kongeveien 1, Kristiansand"
  municipality: "Kristiansand"
  street_id: 12345
```

### Integrations
- In the HA UI go to "Configuration" -> "Integrations" click "+" and search for "avfallsor"

See the `lovelace_example` folder for config example


[commits-shield]: https://img.shields.io/github/commit-activity/y/custom-components/sensor.avfallsor.svg?style=for-the-badge
[commits]: https://github.com/custom-components/sensor.avfallsor/commits/master
[hacs]: https://github.com/custom-components/hacs
[hacsbadge]: https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[exampleimg]: example.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/custom-components/blueprint.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/custom-components/blueprint.svg?style=for-the-badge
[releases]: https://github.com/custom-components/sensor.avfallsor/releases
