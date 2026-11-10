module alarm_top (input F, input C, input G, input W, output A);
    wire apart, shares;
    goat_apart  u_apart  (.F(F), .G(G), .apart(apart));
    goat_shares u_shares (.G(G), .C(C), .W(W), .shares(shares));
    assign A = apart & shares;
endmodule
