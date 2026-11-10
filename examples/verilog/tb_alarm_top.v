`timescale 1ns/1ps
module tb_alarm_top;
    reg F, C, G, W;
    wire A;
    integer i, errors;
    alarm_top uut (.F(F), .C(C), .G(G), .W(W), .A(A));
    wire expected = (~F & G & W) | (~F & G & C) | (F & ~G & ~C) | (F & ~G & ~W);
    initial begin
        $dumpfile("alarm_top.vcd");
        $dumpvars(0, tb_alarm_top);
        errors = 0;
        for (i = 0; i < 16; i = i + 1) begin
            {F, C, G, W} = i[3:0];
            #10;
            if (A !== expected) begin
                $display("FAIL F=%b C=%b G=%b W=%b A=%b expected=%b", F, C, G, W, A, expected);
                errors = errors + 1;
            end
        end
        if (errors == 0) $display("PASS: all 16 cases match");
        $finish;
    end
endmodule
