function set_data_from_json(worksheet, df_json_data) {
    let col_idx = 0;
    for (const [col, rows] of Object.entries(df_json_data)) {
        const col_letter = String.fromCharCode(65 + col_idx);

        let row_idx = 0;
        for (const cell_value of rows) {
            const cell_address = `${col_letter}${row_idx + 1}`;
            const cell = worksheet.getRange(cell_address);
            if (row_idx === 0) {
                cell.setValue(col);
                cell.setCellStyle({
                    bold: true,
                    horizontalAlignment: "center",
                    verticalAlignment: "center",
                    backgroundColor: "#D3D3D3"
                });
            } else {
                cell.setValue(cell_value || "");
            }
            row_idx += 1;
        }
        col_idx += 1;
    }
}

        // const jsonData = [
        //     { name: "Alice", age: 30, city: "New York" },
        //     { name: "Bob", age: 25, city: "London" },
        //     { name: "Charlie", age: 35, city: "Tokyo" }
        // ];

        // worksheet.getRange("A1").setValue("Name");
        // worksheet.getRange("B1").setValue("Age");
        // worksheet.getRange("C1").setValue("City");
        // jsonData.forEach((item, index) => {
        //     worksheet.getRange(`A${index + 2}`).setValue(item.name);
        //     worksheet.getRange(`B${index + 2}`).setValue(item.age);
        //     worksheet.getRange(`C${index + 2}`).setValue(item.city);
        // });