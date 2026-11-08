function r = patch_sim(p)
% PATCH_SIM  Runs the inset-fed patch antenna (same code as Patch_Antenna.m)
% with the values in struct p, and returns the results instead of plotting.
%
% Fields of p (any missing field uses the original value):
%   PL    patch length (mm)          default 29.5
%   PW    patch width (mm)           default 38
%   InL   inset depth (mm)           default 9
%   InW   inset gap width (mm)       default 0.74
%   epsR  substrate permittivity     default 4.3
%   tanD  substrate loss tangent     default 0.025
%   name  folder name for this run   default 'tmp_run'
%
% Output r: freq, s11_dB, f_res, s11_min, bw (1x2, GHz), Dmax_dBi, runtime_s
%
% Run it by itself (just type patch_sim) to simulate the original antenna
% and see its S11 plot and numbers. run_experiments.m calls it with changes.

if nargin < 1
  p = struct();
end

d = struct('PL', 29.5, 'PW', 38, 'InL', 9, 'InW', 0.74, 'epsR', 4.3, ...
           'tanD', 0.025, 'name', 'tmp_run');
fn = fieldnames(d);
for i = 1:numel(fn)
  if ~isfield(p, fn{i})
    p.(fn{i}) = d.(fn{i});
  end
end

%% Setup (same as Patch_Antenna.m lines 13-36)
physical_constants;
unit = 1e-3;
SL = 59; SW = 76; SH = 1.5;
epsR = p.epsR; tanD = p.tanD;
f0 = 2.4e9;
kappa = tanD * 2*pi*f0 * EPS0 * epsR;
PL = p.PL; PW = p.PW;
MW = 2.86; InL = p.InL; InW = p.InW;
SimBox = [200 200 150];

%% FDTD settings (lines 38-43)
fc = 1e9;
FDTD = InitFDTD('NrTs', 40000, 'EndCriteria', 1e-4);
FDTD = SetGaussExcite(FDTD, f0, fc);
BC = {'MUR' 'MUR' 'MUR' 'MUR' 'MUR' 'MUR'};
FDTD = SetBoundaryCond(FDTD, BC);

%% Geometry (lines 45-71)
CSX = InitCSX();
mesh.x = [-SimBox(1)/2 SimBox(1)/2];
mesh.y = [-SimBox(2)/2 SimBox(2)/2];
mesh.z = [-SimBox(3)/3 SimBox(3)*2/3];

CSX = AddMaterial(CSX, 'substrate');
CSX = SetMaterialProperty(CSX, 'substrate', 'Epsilon', epsR, 'Kappa', kappa);
CSX = AddBox(CSX, 'substrate', 0, [-SL/2 -SW/2 0], [SL/2 SW/2 SH]);
mesh.z = [linspace(0, SH, 5) mesh.z];

CSX = AddMetal(CSX, 'gnd');
CSX = AddBox(CSX, 'gnd', 10, [-SL/2 -SW/2 0], [SL/2 SW/2 0]);

CSX = AddMetal(CSX, 'patch');
xin = PL/2 - InL;
CSX = AddBox(CSX, 'patch', 10, [-PL/2 -PW/2 SH], [xin PW/2 SH]);
CSX = AddBox(CSX, 'patch', 10, [xin  MW/2+InW SH], [PL/2  PW/2 SH]);
CSX = AddBox(CSX, 'patch', 10, [xin -PW/2 SH],     [PL/2 -MW/2-InW SH]);
CSX = AddBox(CSX, 'patch', 10, [xin -MW/2 SH], [SL/2 MW/2 SH]);

%% Mesh (lines 73-81)
mesh.y = [mesh.y linspace(-MW/2, MW/2, 5) -MW/2-InW MW/2+InW];
portlen = 10;
mesh.x = [mesh.x xin PL/2 -PL/2 SL/2 -SL/2 SL/2-portlen];
mesh = DetectEdges(CSX, mesh, 'ExcludeProperty', 'patch');
mesh = DetectEdges(CSX, mesh, 'SetProperty', 'patch', '2D_Metal_Edge_Res', 0.5);
mesh = SmoothMesh(mesh, c0/(f0+fc)/unit/20, 1.4);
CSX = DefineRectGrid(CSX, unit, mesh);

%% Port (lines 83-87)
portstart = [SL/2         -MW/2 SH];
portstop  = [SL/2-portlen  MW/2 0];
[CSX, port] = AddMSLPort(CSX, 999, 1, 'patch', portstart, portstop, 0, [0 0 -1], ...
                         'ExcitePort', true, 'FeedShift', 2, 'MeasPlaneShift', portlen/2);

%% Far-field box (lines 89-92)
start = [mesh.x(4)     mesh.y(4)     mesh.z(4)];
stop  = [mesh.x(end-3) mesh.y(end-3) mesh.z(end-3)];
[CSX, nf2ff] = CreateNF2FFBox(CSX, 'nf2ff', start, stop);

%% Run (lines 94-107), no 3D preview so nothing pauses
Sim_Path = p.name;
Sim_CSX = 'inset_patch.xml';
confirm_recursive_rmdir(0);
[status, message, messageid] = rmdir(Sim_Path, 's');
[status, message, messageid] = mkdir(Sim_Path);
WriteOpenEMS([Sim_Path '/' Sim_CSX], FDTD, CSX);
t0 = tic;
RunOpenEMS(Sim_Path, Sim_CSX);
r.runtime_s = toc(t0);

%% S11 over a wider range than the original (1.8 to 3.2 GHz) so shifted dips still show
freq = linspace(1.8e9, 3.2e9, 701);
port = calcPort(port, Sim_Path, freq, 'RefImpedance', 50);
s11_dB = 20*log10(abs(port.uf.ref ./ port.uf.inc));
[s11_min, idx] = min(s11_dB);
f_res = freq(idx);

% -10 dB bandwidth around the dip only
lo = idx; hi = idx;
while lo > 1 && s11_dB(lo-1) < -10, lo = lo - 1; end
while hi < numel(freq) && s11_dB(hi+1) < -10, hi = hi + 1; end
if s11_min < -10
  r.bw = [freq(lo) freq(hi)] / 1e9;
else
  r.bw = [NaN NaN];
end

%% Directivity at this run's own resonance
nf2ff = CalcNF2FF(nf2ff, Sim_Path, f_res, [-180:2:180]*pi/180, [0 90]*pi/180);

r.freq = freq;
r.s11_dB = s11_dB;
r.f_res = f_res / 1e9;
r.s11_min = s11_min;
r.Dmax_dBi = 10*log10(nf2ff.Dmax);
r.p = p;

% typed on its own: show the result instead of returning it
if nargout == 0
  fprintf('Resonance: %.3f GHz, S11 = %.2f dB, Directivity = %.2f dBi\n', r.f_res, r.s11_min, r.Dmax_dBi);
  if ~isnan(r.bw(1))
    fprintf('-10 dB bandwidth: %.3f to %.3f GHz\n', r.bw(1), r.bw(2));
  end
  figure
  plot(freq/1e9, s11_dB, 'r-', 'LineWidth', 2);
  hold on
  plot(freq/1e9, -10*ones(size(freq)), 'k--');
  grid on
  title('S_{11} (patch\_sim)');
  xlabel('Frequency (GHz)');
  ylabel('|S_{11}| (dB)');
  clear r
end
end
