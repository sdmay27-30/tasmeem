%% openEMS value-change experiments for the inset-fed patch antenna
%% ----------------------------------------------------------------
%% Keep this file and patch_sim.m in the same folder as Patch_Antenna.m,
%% open this file in Octave and click Run. No windows pause the script.
%%
%% Runs the original antenna once, then changes one value at a time:
%%   Experiment 1: patch length PL   (29.5 -> 28.5 and 30.5 mm)
%%   Experiment 2: inset depth InL   (9 -> 6 and 12 mm)
%%   Experiment 3: substrate epsR    (4.3 -> 3.38, a Rogers RO4003C value)
%% That is 6 openEMS runs in total. Each one takes about as long as
%% one run of Patch_Antenna.m.
%%
%% Output: exp1_PL.png, exp2_InL.png, exp3_epsR.png (S11 overlays)
%% and experiment_results.txt (the numbers for the slides).

close all
clear
clc
% openEMS is already on the Octave path inside TASMEEM (no addpath needed)

base = struct('name', 'tmp_base');
fprintf('Run 1 of 6: original antenna\n');
R0 = patch_sim(base);

exps = {
  % title,                         field,  new values,  units,  plot range (GHz), file
  'Experiment 1: patch length PL', 'PL',   [28.5 30.5], ' mm',  [2.0 2.8],        'exp1_PL.png'
  'Experiment 2: inset depth InL', 'InL',  [6 12],      ' mm',  [2.2 2.6],        'exp2_InL.png'
  'Experiment 3: substrate epsR',  'epsR', [3.38],      '',     [2.2 3.0],        'exp3_epsR.png'
};
orig = struct('PL', 29.5, 'InL', 9, 'epsR', 4.3);

rows = {'base', 'original', R0};   % every run is added here for the table

run_no = 1;
for e = 1:size(exps, 1)
  [ttl, fld, vals, un, rng, png] = exps{e, :};
  figure
  plot(R0.freq/1e9, R0.s11_dB, 'k-', 'LineWidth', 2);
  hold on
  leg = {sprintf('%s = %g%s (original)', fld, orig.(fld), un)};
  colors = {'r-', 'b-'};
  for v = 1:numel(vals)
    run_no = run_no + 1;
    fprintf('Run %d of 6: %s = %g\n', run_no, fld, vals(v));
    p = struct('name', sprintf('tmp_%s_%g', fld, vals(v)));
    p.(fld) = vals(v);
    R = patch_sim(p);
    plot(R.freq/1e9, R.s11_dB, colors{v}, 'LineWidth', 2);
    leg{end+1} = sprintf('%s = %g%s', fld, vals(v), un);
    rows(end+1, :) = {fld, num2str(vals(v)), R};
  end
  plot(R0.freq/1e9, -10*ones(size(R0.freq)), 'k--');
  leg{end+1} = '-10 dB';
  grid on
  xlim(rng);
  title(ttl);
  xlabel('Frequency (GHz)');
  ylabel('|S_{11}| (dB)');
  legend(leg, 'Location', 'southeast');
  print(png, '-dpng', '-r150');
end

%% Write the results table
fid = fopen('experiment_results.txt', 'w');
fmt = '%-6s %-9s %-10s %-10s %-20s %-10s %-8s\n';
fprintf(fid, fmt, 'Param', 'Value', 'f_res', 'S11 min', '-10 dB bandwidth', 'Dmax', 'Time');
fprintf(fid, fmt, '', '', '(GHz)', '(dB)', '(GHz)', '(dBi)', '(s)');
for k = 1:size(rows, 1)
  R = rows{k, 3};
  if isnan(R.bw(1))
    bw = 'none';
  else
    bw = sprintf('%.3f to %.3f', R.bw(1), R.bw(2));
  end
  fprintf(fid, fmt, rows{k, 1}, rows{k, 2}, sprintf('%.3f', R.f_res), sprintf('%.2f', R.s11_min), ...
          bw, sprintf('%.2f', R.Dmax_dBi), sprintf('%.0f', R.runtime_s));
end
fclose(fid);
type('experiment_results.txt');
disp('Done. Send the three PNG files and experiment_results.txt.');
