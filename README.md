# sensor.avfallsor
Simple sensor for avfallsor

config example
Gå til https://avfallsor.no/tommekalender/ fyll inn adresse og husnummber, trykk vis tømmekalender
siden du blir redirected til har en url some ser noe sånn ut https://avfallsor.no/tommekalender/?id=12345&kommune=Kristiansand
bruk id og kommune under som sensor innstillinger.
````
sensor:
- platform: avfallsor
  streetid: 1234
  kommune: Kristiansand
````
