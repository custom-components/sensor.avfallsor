# sensor.avfallsor
Simple sensor for avfallsor


The sensor tries to find the your address (to find the pickup dates for your address) in this order:
1. street_id and kommune
2. Address
3. Lat and lon that you entered when you setup home assistant.

So minimal example could be.
````
sensor:
- platform: avfallsor
````

Full example.
```
sensor:
- platform: avfallsor
  address: "Kongeveien 1, Kristiansand"
  kommune: "Kristiansand"
  street_id: 12345
```

Go to https://avfallsor.no/tommekalender/ enter the address and the hour number, press "vis tømmekalender" after that you get redirect to url that looks something like this: ```https://avfallsor.no/tommekalender/?id=12345&kommune=Kristiansand``` gram the id and the kommune in the url.
