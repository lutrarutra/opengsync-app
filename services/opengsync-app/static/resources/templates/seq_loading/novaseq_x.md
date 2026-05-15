## 0. Parameters
- `NaOH`: number : {naoh} : 8.5
- `Preload`: number : {preload} : 127.5
- `Pool Volume`: number : {pool_volume} : 34
- `Phi X`: list : {phi_x} : 

## 1. Prepare NovaSeq X
1. [ ] Check storage space on the sequencer (>15GB on SBS drive - 1.5B 100 cycles)
2. [ ] Thaw reagent cartridge (`4 hours`) RT waterbath
3. [ ] Thaw Lyo Insert at RT (`10 minutes`)
4. [ ] Thaw Pre-load Buffer at RT (`10 minutes`)
5. [ ] Locate buffer cartridge
6. [ ] Locate library tube strip and holder
7. [ ] Thaw `300pM` PhiX stock
8. [ ] Thaw library
9. [ ] Set flowcell at RT for `15` minutes
10. [ ] Prepare 1N NaOH (`900µl` nuclease free water + `100µl` 10N NaOH)
11. [ ] Prepare 0,2N NaOH (`800µl` nuclease free water + `200µl` 1N NaOH)
12. [ ] Combine the Library with PhiX and denature with NaOH

{{ lane_table }}

## 2. Pre-load Buffer
1. [ ] Cap and vortex briefly
2. [ ] Incubate at RT for `5` minutes
3. [ ] Add Pre-load Buffer LOT:______________________

{{ pre_load_buffer_table }}

## 3. Load library
1. [ ] Cap and vortex briefly
2. [ ] Transfer `165µl` to each sample tube (Make sure to not create any bubbles)
3. [ ] Insert the library tube strip into the reagent cartridge
4. [ ] Log into sercive software (PW on todo list) --> Click sequencing and choose the side
5. [ ] Select run manual and put the BSF number as Runnumber and add the sequencing configuration
6. [ ] Select the nobackup BSF as output folder
7. [ ] Put in the flowcell and catrtridges and empty the waste bottles
8. [ ] Update reagent Kits in To do list
