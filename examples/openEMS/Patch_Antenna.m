%% Inset-Fed Patch Antenna (same design as the CST build)
%% -----------------------------------------------------
%% 2.4 GHz microstrip patch on FR-4 with a 50 ohm inset feed line.
%% Dimensions match the CST model: SL 59, SW 76, SH 1.5, PL 29.5, PW 38,
%% MW 2.86, InL 9, InW 0.74 (all mm), FR-4 epsR 4.3.
%% Based on openEMS's Simple_Patch_Antenna.m tutorial.

close all
clear
clc
% openEMS is already on the Octave path inside TASMEEM (no addpath needed)

%% Setup
physical_constants;
unit = 1e-3; % all lengths in mm

% substrate (FR-4)
SL = 59;      % substrate length (x)
SW = 76;      % substrate width (y)
SH = 1.5;     % substrate thickness
epsR = 4.3;
tanD = 0.025;
f0 = 2.4e9;   % center frequency
kappa = tanD * 2*pi*f0 * EPS0 * epsR;

% patch
PL = 29.5;    % patch length (x), sets the resonant frequency
PW = 38;      % patch width (y)

% feed line and insets
MW = 2.86;    % 50 ohm microstrip width
InL = 9;      % inset depth
InW = 0.74;   % inset gap width on each side of the feed

% simulation box (air around the antenna)
SimBox = [200 200 150];

%% FDTD settings
fc = 1e9;     % pulse covers about 1.4 to 3.4 GHz
FDTD = InitFDTD('NrTs', 40000, 'EndCriteria', 1e-4);
FDTD = SetGaussExcite(FDTD, f0, fc);
BC = {'MUR' 'MUR' 'MUR' 'MUR' 'MUR' 'MUR'};
FDTD = SetBoundaryCond(FDTD, BC);

%% Geometry
CSX = InitCSX();

mesh.x = [-SimBox(1)/2 SimBox(1)/2];
mesh.y = [-SimBox(2)/2 SimBox(2)/2];
mesh.z = [-SimBox(3)/3 SimBox(3)*2/3];

% substrate
CSX = AddMaterial(CSX, 'substrate');
CSX = SetMaterialProperty(CSX, 'substrate', 'Epsilon', epsR, 'Kappa', kappa);
CSX = AddBox(CSX, 'substrate', 0, [-SL/2 -SW/2 0], [SL/2 SW/2 SH]);
mesh.z = [linspace(0, SH, 5) mesh.z];   % 4 cells through the substrate

% ground plane (bottom)
CSX = AddMetal(CSX, 'gnd');
CSX = AddBox(CSX, 'gnd', 10, [-SL/2 -SW/2 0], [SL/2 SW/2 0]);

% patch with two inset notches, built from three boxes (no boolean cuts needed)
CSX = AddMetal(CSX, 'patch');
xin = PL/2 - InL;   % where the notches start
% main body
CSX = AddBox(CSX, 'patch', 10, [-PL/2 -PW/2 SH], [xin PW/2 SH]);
% the two side pieces next to the notches
CSX = AddBox(CSX, 'patch', 10, [xin  MW/2+InW SH], [PL/2  PW/2 SH]);
CSX = AddBox(CSX, 'patch', 10, [xin -PW/2 SH],     [PL/2 -MW/2-InW SH]);
% feed line from inside the inset out to the board edge
CSX = AddBox(CSX, 'patch', 10, [xin -MW/2 SH], [SL/2 MW/2 SH]);

%% Mesh
% extra lines across the feed and the small inset gaps
mesh.y = [mesh.y linspace(-MW/2, MW/2, 5) -MW/2-InW MW/2+InW];
portlen = 10;
mesh.x = [mesh.x xin PL/2 -PL/2 SL/2 -SL/2 SL/2-portlen];
mesh = DetectEdges(CSX, mesh, 'ExcludeProperty', 'patch');
mesh = DetectEdges(CSX, mesh, 'SetProperty', 'patch', '2D_Metal_Edge_Res', 0.5);
mesh = SmoothMesh(mesh, c0/(f0+fc)/unit/20, 1.4);
CSX = DefineRectGrid(CSX, unit, mesh);

% 50 ohm microstrip port at the board edge, feeding toward the patch
portstart = [SL/2         -MW/2 SH];
portstop  = [SL/2-portlen  MW/2 0];
[CSX, port] = AddMSLPort(CSX, 999, 1, 'patch', portstart, portstop, 0, [0 0 -1], ...
                         'ExcitePort', true, 'FeedShift', 2, 'MeasPlaneShift', portlen/2);

% far-field box, 3 cells inside the boundary
start = [mesh.x(4)     mesh.y(4)     mesh.z(4)];
stop  = [mesh.x(end-3) mesh.y(end-3) mesh.z(end-3)];
[CSX, nf2ff] = CreateNF2FFBox(CSX, 'nf2ff', start, stop);

%% Run
Sim_Path = 'tmp_Inset_Patch';
Sim_CSX = 'inset_patch.xml';

% clear old results and make an empty folder (works on openEMS v0.0.36)
confirm_recursive_rmdir(0);
[status, message, messageid] = rmdir(Sim_Path, 's');
[status, message, messageid] = mkdir(Sim_Path);
WriteOpenEMS([Sim_Path '/' Sim_CSX], FDTD, CSX);

% preview the structure (close the viewer window to continue)
CSXGeomPlot([Sim_Path '/' Sim_CSX]);

RunOpenEMS(Sim_Path, Sim_CSX);

%% Results: S11 (same 2.2 to 2.6 GHz range as CST)
freq = linspace(2.2e9, 2.6e9, 401);
port = calcPort(port, Sim_Path, freq, 'RefImpedance', 50);
s11 = port.uf.ref ./ port.uf.inc;
s11_dB = 20*log10(abs(s11));

figure
plot(freq/1e9, s11_dB, 'r-', 'LineWidth', 2);
hold on
plot(freq/1e9, -10*ones(size(freq)), 'k--');
grid on
title('S_{11} (openEMS)');
xlabel('Frequency (GHz)');
ylabel('|S_{11}| (dB)');

% resonance and -10 dB bandwidth
[s11_min, idx] = min(s11_dB);
f_res = freq(idx);
below = freq(s11_dB < -10);
disp(['Resonance: ' num2str(f_res/1e9, '%.3f') ' GHz, S11 = ' num2str(s11_min, '%.2f') ' dB']);
if ~isempty(below)
  disp(['-10 dB bandwidth: ' num2str(below(1)/1e9, '%.3f') ' to ' num2str(below(end)/1e9, '%.3f') ' GHz']);
end

% feed impedance
Zin = port.uf.tot ./ port.if.tot;
figure
plot(freq/1e9, real(Zin), 'k-', freq/1e9, imag(Zin), 'r--', 'LineWidth', 2);
grid on
title('Feed point impedance');
xlabel('Frequency (GHz)');
ylabel('Z_{in} (Ohm)');
legend('real', 'imag');

%% Results: radiation pattern at 2.4 GHz (same as the CST farfield monitor)
nf2ff = CalcNF2FF(nf2ff, Sim_Path, 2.4e9, [-180:2:180]*pi/180, [0 90]*pi/180);
disp(['Directivity: ' num2str(10*log10(nf2ff.Dmax), '%.2f') ' dBi']);

figure
plotFFdB(nf2ff, 'xaxis', 'theta', 'param', [1 2]);

thetaRange = (0:2:180);
phiRange = (0:2:360) - 180;
nf2ff = CalcNF2FF(nf2ff, Sim_Path, 2.4e9, thetaRange*pi/180, phiRange*pi/180, 'Outfile', '3D_Pattern.h5');
figure
plotFF3D(nf2ff, 'logscale', -20);
