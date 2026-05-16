#!/usr/bin/env bash
set -eo pipefail

cd /home/pingfan/PACT/excavator_testbed

configs=(
  testbed/configs/act_yulong_v2_2_operator_first_4p_dig_cut_qvel.yaml
  testbed/configs/act_yulong_v2_2_operator_first_4p_carry_qvel.yaml
  testbed/configs/act_yulong_v2_2_operator_first_4p_dump_qvel.yaml
  testbed/configs/act_yulong_v2_2_operator_first_4p_return_qvel.yaml
)

for cfg in "${configs[@]}"; do
  echo "===== START $(date -Is) ${cfg} ====="
  python -m testbed.cli.train --config "${cfg}"
  echo "===== DONE  $(date -Is) ${cfg} ====="
done
