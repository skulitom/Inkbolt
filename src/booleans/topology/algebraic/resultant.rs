//! Eliminate the second parameter with a fraction-free Sylvester determinant.
use super::*;
use roots::{multiply, quotient, subtract};

fn coordinate(a: &Cubic, b: &Cubic, axis: usize) -> Vec<Poly> {
    let ap = curves::coefficients(a);
    let bp = curves::coefficients(b);
    let mut first: Poly = ap.iter().map(|v| v[axis].clone()).collect();
    first[0] -= &bp[0][axis];
    let mut out = vec![trim(first)];
    out.extend(bp.iter().skip(1).map(|v| trim(vec![-v[axis].clone()])));
    while out.last().is_some_and(Vec::is_empty) {
        out.pop();
    }
    out
}

fn eliminate(f: &[Poly], g: &[Poly], budget: &mut Budget) -> Result<Poly, Error> {
    if f.is_empty() || g.is_empty() {
        return Ok(vec![]);
    }
    let (m, n) = (f.len() - 1, g.len() - 1);
    let size = m + n;
    if size == 0 {
        return Ok(vec![]);
    }
    let mut matrix = vec![vec![vec![]; size]; size];
    for (row, values) in matrix.iter_mut().take(n).enumerate() {
        for (column, coefficient) in f.iter().rev().enumerate() {
            values[row + column] = coefficient.clone();
        }
    }
    for (row, values) in matrix.iter_mut().skip(n).enumerate() {
        for (column, coefficient) in g.iter().rev().enumerate() {
            values[row + column] = coefficient.clone();
        }
    }
    let mut previous = vec![super::n(1)];
    let mut negative = false;
    for k in 0..size - 1 {
        let Some(row) = (k..size).find(|&row| !matrix[row][k].is_empty()) else {
            return Ok(vec![]);
        };
        if row != k {
            matrix.swap(row, k);
            negative = !negative;
        }
        let pivot = matrix[k][k].clone();
        for i in k + 1..size {
            for j in k + 1..size {
                let lhs = multiply(&pivot, &matrix[i][j], budget)?;
                let rhs = multiply(&matrix[i][k], &matrix[k][j], budget)?;
                matrix[i][j] = quotient(subtract(lhs, &rhs), &previous, budget)?;
            }
            matrix[i][k].clear();
        }
        previous = pivot;
    }
    let out = matrix.pop().unwrap().pop().unwrap();
    Ok(if negative {
        out.into_iter().map(|v| -v).collect()
    } else {
        out
    })
}

pub(super) fn contacts(a: &Cubic, b: &Cubic, budget: &mut Budget) -> Result<Vec<(R, R)>, Error> {
    let p = eliminate(&coordinate(a, b, 0), &coordinate(a, b, 1), budget)?;
    let mut out = Vec::new();
    for t in rational_roots(&p, budget)?.into_iter().filter(unit) {
        let point = at(a, &t);
        for u in preimages(b, &point, budget)?.into_iter().filter(unit) {
            // Elimination can have spurious roots from degree drops. Only an
            // exact equality of both original coordinates is a contact.
            if at(b, &u) == point {
                out.push((t.clone(), u));
            }
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn different_nonlinear_parameters_have_a_third_order_contact() {
        let a = [[9, 7], [19, 10], [32, 4], [48, 16]].map(|p| p.map(n));
        let b = [[4, 16], [8, 4], [18, 10], [34, 7]].map(|p| p.map(n));
        let mut budget = Budget::default();
        assert!(
            contacts(&a, &b, &mut budget)
                .unwrap()
                .contains(&(n(1) / n(3), n(2) / n(3)))
        );
        assert!(
            contacts(&b, &a, &mut budget)
                .unwrap()
                .contains(&(n(2) / n(3), n(1) / n(3)))
        );
        let reversed = std::array::from_fn(|i| b[3 - i].clone());
        assert!(
            contacts(&a, &reversed, &mut budget)
                .unwrap()
                .contains(&(n(1) / n(3), n(1) / n(3)))
        );
        assert!(contacts(&a, &a, &mut budget).unwrap().is_empty());
    }

    #[test]
    fn quadratic_degree_reduction_keeps_tangency() {
        let a = [[0, 6], [1, 6], [3, 7], [6, 9]].map(|p| p.map(n));
        let b = [[0, 7], [1, 5], [3, 7], [6, 13]].map(|p| p.map(n));
        assert!(
            contacts(&a, &b, &mut Budget::default())
                .unwrap()
                .contains(&(n(1) / n(3), n(1) / n(3)))
        );
    }
}
