module goat_shares (input G, input C, input W, output shares);
    assign shares = G ? (C | W) : (~C | ~W);
endmodule
