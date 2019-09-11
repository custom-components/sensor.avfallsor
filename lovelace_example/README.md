As Avfall Sør is a norwegian service,
the given examples include some norwegian words.

To get notified when to put the waste containers
out on the street for garbage collection,
make an input boolean like:

````
input_boolean:
  notify_avfallsor:
    name: 'Trash notification'
    initial: 'off'
    icon: mdi:bell-ring
````

Then a couple of nice automations to turn on
the input boolean and get notifications:

````
automation:
  - id: mixed_bio_waste
    alias: 'Weekly notification to put waste containers out on the street'
    initial_state: true
    hide_entity: false
    trigger:
      platform: time
      at: '18:00:00'
    condition:
      - condition: state
        entity_id: input_boolean.notify_avfallsor
        state: 'off'
      - condition: template
        value_template: "{{ states('sensor.avfallsor_mixed') == '1' }}"
      - condition: template
        value_template: "{{ states('sensor.avfallsor_bio') == '1' }}"
    action:
      - service: homeassistant.turn_on
        entity_id: input_boolean.notify_avfallsor
      - service: notify.my_pushbullet
        data:
          message: "Sett ut restavfall og matavfall."

  - id: paper_waste
    alias: 'Extra notification for paper container'
    initial_state: true
    hide_entity: false
    trigger:
      platform: time
      at: '18:00:15'
    condition:
      - condition: state
        entity_id: input_boolean.notify_avfallsor
        state: 'on'
      - condition: template
        value_template: "{{ states('sensor.avfallsor_paper') == '1' }}"
    action:
      - service: notify.my_pushbullet
        data:
          message: "Sett ut papiravfall."

  - id: metal_waste
    alias: 'Extra notification for glass and metal container'
    initial_state: true
    hide_entity: false
    trigger:
      platform: time
      at: '18:00:15'
    condition:
      - condition: state
        entity_id: input_boolean.notify_avfallsor
        state: 'on'
      - condition: template
        value_template: "{{ states('sensor.avfallsor_metal') == '1' }}"
    action:
      - service: notify.my_pushbullet
        data:
          message: "Sett ut glass og metallavfall."
````

And at last a lovelace card.
This is an example using entities-card
and custom plugin multiple-entity-row.

![Simple](/lovelace_example/avfallsor.PNG)

````
title: My home
resources:
  - url: /community_plugin/lovelace-multiple-entity-row/multiple-entity-row.js
    type: js
views:
  - title: Avfall Sør
    icon: mdi:delete
    cards:
      - type: entities
        title: Avfall Sør
        show_header_toggle: false
        entities:
          - entity: sensor.avfallsor_mixed
            type: custom:multiple-entity-row
            name: Restavfall
            icon: mdi:delete
            unit: dg
            primary:
              entity: sensor.avfallsor_mixed
              name: Tømmedato
              attribute: next garbage pickup
          - entity: sensor.avfallsor_bio
            type: custom:multiple-entity-row
            name: Matavfall
            icon: mdi:delete
            unit: dg
            primary:
              entity: sensor.avfallsor_bio
              name: Tømmedato
              attribute: next garbage pickup
          - entity: sensor.avfallsor_paper
            type: custom:multiple-entity-row
            name: Papir og plastavfall
            icon: mdi:delete
            unit: dg
            primary:
              entity: sensor.avfallsor_paper
              name: Tømmedato
              attribute: next garbage pickup
          - entity: sensor.avfallsor_metal
            type: custom:multiple-entity-row
            name: Glass og metallavfall
            icon: mdi:delete
            unit: dg
            primary:
              entity: sensor.avfallsor_metal
              name: Tømmedato
              attribute: next garbage pickup
          - entity: input_boolean.notify_avfallsor
            name: Sett ut avfallsdunker!
````
