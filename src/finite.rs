//! Reject nonfinite typed input before JSON can normalize it to null in retry hashes.
use serde::{Serialize, Serializer, ser};

struct Check;
type Result<T> = std::result::Result<T, serde_json::Error>;

pub(crate) fn check(value: &impl Serialize) -> std::result::Result<(), crate::Error> {
    value.serialize(Check).map_err(|_| {
        crate::Error::new(
            "INVALID_REQUEST",
            "Session action numbers must be finite before calculating retry or proposal identity",
        )
    })
}

macro_rules! scalar {
    ($($method:ident($ty:ty)),* $(,)?) => { $(fn $method(self,_value:$ty)->Result<()> {Ok(())})* };
}
impl Serializer for Check {
    type Ok = ();
    type Error = serde_json::Error;
    type SerializeSeq = Self;
    type SerializeTuple = Self;
    type SerializeTupleStruct = Self;
    type SerializeTupleVariant = Self;
    type SerializeMap = Self;
    type SerializeStruct = Self;
    type SerializeStructVariant = Self;
    scalar!(
        serialize_bool(bool),
        serialize_i8(i8),
        serialize_i16(i16),
        serialize_i32(i32),
        serialize_i64(i64),
        serialize_i128(i128),
        serialize_u8(u8),
        serialize_u16(u16),
        serialize_u32(u32),
        serialize_u64(u64),
        serialize_u128(u128),
        serialize_char(char),
        serialize_str(&str),
        serialize_bytes(&[u8])
    );
    fn serialize_f32(self, value: f32) -> Result<()> {
        self.serialize_f64(value as f64)
    }
    fn serialize_f64(self, value: f64) -> Result<()> {
        if value.is_finite() {
            Ok(())
        } else {
            Err(ser::Error::custom("nonfinite number"))
        }
    }
    fn serialize_none(self) -> Result<()> {
        Ok(())
    }
    fn serialize_some<T: Serialize + ?Sized>(self, value: &T) -> Result<()> {
        value.serialize(self)
    }
    fn serialize_unit(self) -> Result<()> {
        Ok(())
    }
    fn serialize_unit_struct(self, _name: &'static str) -> Result<()> {
        Ok(())
    }
    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
    ) -> Result<()> {
        Ok(())
    }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Result<()> {
        value.serialize(self)
    }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        value: &T,
    ) -> Result<()> {
        value.serialize(self)
    }
    fn serialize_seq(self, _len: Option<usize>) -> Result<Self> {
        Ok(self)
    }
    fn serialize_tuple(self, _len: usize) -> Result<Self> {
        Ok(self)
    }
    fn serialize_tuple_struct(self, _name: &'static str, _len: usize) -> Result<Self> {
        Ok(self)
    }
    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self> {
        Ok(self)
    }
    fn serialize_map(self, _len: Option<usize>) -> Result<Self> {
        Ok(self)
    }
    fn serialize_struct(self, _name: &'static str, _len: usize) -> Result<Self> {
        Ok(self)
    }
    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Self> {
        Ok(self)
    }
}
macro_rules! sequence {
    ($trait:ident, $method:ident) => {
        impl ser::$trait for Check {
            type Ok = ();
            type Error = serde_json::Error;
            fn $method<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
                value.serialize(Check)
            }
            fn end(self) -> Result<()> {
                Ok(())
            }
        }
    };
}
sequence!(SerializeSeq, serialize_element);
sequence!(SerializeTuple, serialize_element);
sequence!(SerializeTupleStruct, serialize_field);
sequence!(SerializeTupleVariant, serialize_field);
impl ser::SerializeMap for Check {
    type Ok = ();
    type Error = serde_json::Error;
    fn serialize_key<T: Serialize + ?Sized>(&mut self, key: &T) -> Result<()> {
        key.serialize(Check)
    }
    fn serialize_value<T: Serialize + ?Sized>(&mut self, value: &T) -> Result<()> {
        value.serialize(Check)
    }
    fn end(self) -> Result<()> {
        Ok(())
    }
}
macro_rules! fields {
    ($trait:ident) => {
        impl ser::$trait for Check {
            type Ok = ();
            type Error = serde_json::Error;
            fn serialize_field<T: Serialize + ?Sized>(
                &mut self,
                _key: &'static str,
                value: &T,
            ) -> Result<()> {
                value.serialize(Check)
            }
            fn end(self) -> Result<()> {
                Ok(())
            }
        }
    };
}
fields!(SerializeStruct);
fields!(SerializeStructVariant);
